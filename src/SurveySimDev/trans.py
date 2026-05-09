#!/usr/bin/env python
'''State-transition based scheduler demonstration
'''

import numpy as np
from transitions import Machine


MODE_VIS, MODE_NUV, MODE_NIR = 0, 1, 2
# observingModes extras:
#  int_factor_x: intTime multiplier per char mode (just for a mockup)
#  comp_bound_x: lower bound of completeness per mode (just for a mockup)

specs = {
    'eta':          0.4,             # mean number of earths per star
    'missionLife':  5 * 365.25,      # days -- total mission duration
    'n_star':       30,              # number of stars in the simulated catalog
    'seed':         0,              # RNG seed; 0 means unseeded (random)
    'n_det_remove': 4,               # failed det attempts before retiring a star
    'n_char_remove': 2,              # char attempts per mode before retiring
    'intCutoff':      60.0,            # days -- skip char observations longer than this
    'revisit_wait': 0.3 * 365.25,   # days -- min gap after any detection attempt
    'gap_required': 0.5 * 365.25,   # days -- min temporal baseline for orbit determination
    'obs_overhead':  0.2,            # days -- overhead added to every observation
    'char_overhead': 0.8,            # days -- additional overhead for characterizations
    'state_initial': {'*': 'unobserved'},
    'state_transitions': [
        {'trigger': 'begin_obs',         'source': 'unobserved', 'dest': 'observing'},
        {'trigger': 'first_det_success', 'source': 'observing',  'dest': 'orbit_det'},
        {'trigger': 'give_up_obs',       'source': 'observing',  'dest': 'retired'},
        {'trigger': 'find_orbit',        'source': 'orbit_det',  'dest': 'char_vis',
             'conditions': ['has_orbit', 'has_sufficient_gap']},
        {'trigger': 'give_up_orbit_det', 'source': 'orbit_det',  'dest': 'retired'},
        {'trigger': 'advance_char_vis',  'source': 'char_vis',   'dest': 'char_nuv',  'conditions': 'vis_char_succeeded'},
        {'trigger': 'retire_vis',        'source': 'char_vis',   'dest': 'retired',   'conditions': 'vis_char_exhausted'},
        {'trigger': 'advance_char_nuv',  'source': 'char_nuv',   'dest': 'char_nir',  'conditions': 'nuv_char_succeeded'},
        {'trigger': 'retire_nuv',        'source': 'char_nuv',   'dest': 'retired',   'conditions': 'nuv_char_exhausted'},
        {'trigger': 'succeed',           'source': 'char_nir',   'dest': 'success',   'conditions': 'all_char_succeeded'},
        {'trigger': 'retire_nir',        'source': 'char_nir',   'dest': 'retired',   'conditions': 'nir_char_exhausted'},
        {'trigger': 'end_mission', 'source': ['char_nuv', 'char_nir'], 'dest': 'partial'},
        {'trigger': 'end_mission', 'source': ['orbit_det', 'char_vis'], 'dest': 'found'},
        {'trigger': 'end_mission', 'source': 'observing', 'dest': 'unknown'},
    ],
    'observingModes': [
        {
         'instName': 'imaging_BroadbandVisible_500',
         'systName': 'VVC500',
         'tag': 'DET',
         'int_factor_x': 1.0,
         'comp_bound_x': 0.1,
         'detection': True,
         'lam': 500,
         'SNR': 7,
         },
        {
         'instName': 'spectro910_R70_EMCCD',
         'systName': 'VVC575',
         'tag': 'VIS',
         'int_factor_x': 1.2,
         'comp_bound_x': 0.8,
         'detection': False,
         'lam': 910,
         'SNR': 5.0,
         },
        {
         'instName': 'spectro_NUV310_EMCCD',
         'systName': 'VVC575',
         'tag': 'NUV',
         'int_factor_x': 1.0,
         'comp_bound_x': 0.9,
         'detection': False,
         'lam': 310,
         'SNR': 5.0
         },
        {
         'instName': 'spectro1500_R40_EMCCD',
         'systName': 'VVC575',
         'tag': 'NIR',
         'int_factor_x': 2.0,
         'comp_bound_x': 0.5,
         'detection': False,
         'lam': 1500,
         'SNR': 8.5
         },
  ],
}


def _states_from_transitions(transitions):
    '''Derive the set of state names from a transitions list.'''
    states = set()
    for t in transitions:
        for endpoint in (t['source'], t['dest']):
            if isinstance(endpoint, list):
                states.update(endpoint)
            else:
                states.add(endpoint)
    return sorted(states)


class SimulatedUniverse:
    def __init__(self, *, specs):
        n_star = specs['n_star']
        seed = None if specs['seed'] == 0 else specs['seed']
        rng = np.random.default_rng(seed)
        self.eta = specs['eta']
        self.n_star = n_star
        self.earths = rng.poisson(self.eta, size=n_star)
        self.dist = rng.uniform(1.0, 10.0, size=n_star)
        # detection mode stuff
        self.det_mode = [om for om in specs['observingModes'] if om['detection']][0]
        det_raw = 5.0 / self.dist + rng.uniform(-0.1, 0.1, size=n_star)
        self.det_comp = np.clip(det_raw, self.det_mode['comp_bound_x'], 0.95)
        # char mode stuff
        # independent completeness per star and per char mode
        self.char_modes = [om for om in specs['observingModes'] if not om['detection']]
        char_raw = np.column_stack([rng.uniform(om['comp_bound_x'], 1.0, size=n_star)
                                    for om in self.char_modes])
        self.char_comp = np.clip(char_raw, 0.05, 1.0)


class OpticalSystem:
    def __init__(self, SU, specs):
        self._dist = SU.dist
        self.obs_overhead  = specs['obs_overhead']
        self.char_overhead = specs['char_overhead']
        # promote to here
        self.det_mode = SU.det_mode
        self.char_modes = SU.char_modes 
        self.n_mode = len(SU.char_modes)

    def calc_intTime(self, star_num, mode=-1):
        t = 0.5 * self._dist[star_num] ** 2
        if mode >= 0:
            t *= self.char_modes[mode]['int_factor_x']
            t += self.char_overhead
        t += self.obs_overhead
        return float(t)


class TimeKeeping:
    def __init__(self, specs):
        self.missionLife = specs['missionLife']
        self.total_time = 0.0

    def allocate(self, days):
        self.total_time += days

    def finished(self):
        return self.total_time >= self.missionLife

    @property
    def current_time(self):
        return self.total_time


class StarInfo:
    n_mode = None
    def __init__(self, star_num, earths, gap_required, n_det_remove, n_char_remove):
        if not self.n_mode:
            RuntimeError('StarInfo needs its n_mode set')
        self.star_num = star_num
        self.earths = earths
        self.gap_required = gap_required
        self.n_det_remove = n_det_remove
        self.n_char_remove = n_char_remove
        self.n_det = 0
        self.n_det_ok = 0
        self.n_char    = np.zeros(self.n_mode, dtype=int)
        self.n_char_ok = np.zeros(self.n_mode, dtype=int)
        self.t_det_first = None
        self.t_det_last = None
        self.t_det_attempt = None   # time of last detection attempt (success or failure)

    # --- condition methods called by transitions ---

    def has_orbit(self):
        '''Enough points for orbit determination'''
        return self.n_det_ok >= 3

    def has_sufficient_gap(self):
        '''Orbit determination span criterion met'''
        if self.t_det_first is None or self.t_det_last is None:
            return False
        return (self.t_det_last - self.t_det_first) >= self.gap_required

    def vis_char_succeeded(self):
        '''VIS characterization succeeded at least once'''
        return self.n_char_ok[MODE_VIS] >= 1

    def nuv_char_succeeded(self):
        '''NUV characterization succeeded at least once'''
        return self.n_char_ok[MODE_NUV] >= 1

    def nir_char_succeeded(self):
        '''NIR characterization succeeded at least once'''
        return self.n_char_ok[MODE_NIR] >= 1

    def all_char_succeeded(self):
        '''All three characterization modes succeeded at least once'''
        return bool(np.all(self.n_char_ok >= 1))

    def vis_char_exhausted(self):
        '''VIS attempts exhausted with no success'''
        return self.n_char[MODE_VIS] >= self.n_char_remove and self.n_char_ok[MODE_VIS] == 0

    def nuv_char_exhausted(self):
        '''NUV attempts exhausted with no success'''
        return self.n_char[MODE_NUV] >= self.n_char_remove and self.n_char_ok[MODE_NUV] == 0

    def nir_char_exhausted(self):
        '''NIR attempts exhausted with no success'''
        return self.n_char[MODE_NIR] >= self.n_char_remove and self.n_char_ok[MODE_NIR] == 0

    def detection_exhausted(self):
        '''No more det attempts allowed (0 successes)'''
        return self.n_det >= self.n_det_remove and self.n_det_ok == 0

    def orbit_det_exhausted(self):
        '''Detection attempts exhausted without reaching orbit (3 successes)'''
        return self.n_det >= self.n_det_remove and not self.has_orbit()

    # --- state-entry callbacks auto-discovered by transitions ---

    def on_enter_observing(self):
        print(f"  Star {self.star_num:2d}: unobserved  -> OBSERVING")

    def on_enter_orbit_det(self):
        print(f"  Star {self.star_num:2d}: observing   -> ORBIT_DET      "
              f"(n_det_ok={self.n_det_ok}, t={self.t_det_first:.1f}d)")

    def on_enter_char_vis(self):
        print(f"  Star {self.star_num:2d}: orbit_det   -> CHAR_VIS       "
              f"(earths={self.earths})")

    def on_enter_char_nuv(self):
        print(f"  Star {self.star_num:2d}: char_vis    -> CHAR_NUV       "
              f"(nok_vis={self.n_char_ok[MODE_VIS]})")

    def on_enter_char_nir(self):
        print(f"  Star {self.star_num:2d}: char_nuv    -> CHAR_NIR       "
              f"(nok_nuv={self.n_char_ok[MODE_NUV]})")

    def on_enter_success(self):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: char_nir    -> SUCCESS        "
              f"(ok/att per mode: [{counts}])")

    def on_enter_partial(self):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: -> PARTIAL  (char ok/att=[{counts}])")

    def on_enter_found(self):
        print(f"  Star {self.star_num:2d}: -> FOUND    "
              f"(n_det_ok={self.n_det_ok}/{self.n_det})")

    def on_enter_unknown(self):
        print(f"  Star {self.star_num:2d}: -> UNKNOWN  "
              f"({self.n_det} det attempts, 0 successes)")

    def on_enter_retired(self):
        if np.any(self.n_char > 0):
            counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
            note = f"char ok/att=[{counts}]"
        else:
            note = f"never detected ({self.n_det} attempts)"
        print(f"  Star {self.star_num:2d}: -> RETIRED  ({note})")


class SurveySimulation:
    def __init__(self, sim_universe, optical_system, time_keeping, specs):
        self.su = sim_universe
        self.os = optical_system
        self.tk = time_keeping
        self.revisit_wait  = specs['revisit_wait']
        self.gap_required  = specs['gap_required']
        self.intCutoff       = specs['intCutoff']
        self.n_det_remove  = specs['n_det_remove']
        self.n_char_remove = specs['n_char_remove']
        self._specs = specs
        seed = None if specs['seed'] == 0 else specs['seed']
        self._rng = np.random.default_rng(seed)
        self.state_history = []   # one n_star state-vector per observation
        self.DRM = []             # one record per observation
        # set up the class (globally)
        StarInfo.n_mode = self.os.n_mode
        self.stars = [
            StarInfo(
                star_num=i,
                earths=int(sim_universe.earths[i]),
                gap_required=self.gap_required,
                n_det_remove=self.n_det_remove,
                n_char_remove=self.n_char_remove,
            )
            for i in range(sim_universe.n_star)
        ]
        self._build_machines()

    def _build_machines(self):
        transitions = self._specs['state_transitions']
        initial = self._specs['state_initial']['*']
        states = _states_from_transitions(transitions)
        self._machine = Machine(
            model=self.stars,
            states=states,
            transitions=transitions,
            initial=initial,
            ignore_invalid_triggers=True,
            auto_transitions=False,
        )

    def _det_eligible(self, star):
        if not (star.is_unobserved() or star.is_observing() or star.is_orbit_det()):
            return False
        if star.t_det_attempt is None:
            return True
        return self.tk.current_time - star.t_det_attempt >= self.revisit_wait

    def next_target(self):
        char_cands = []
        for s in self.stars:
            if   s.is_char_vis(): char_cands.append((s, MODE_VIS))
            elif s.is_char_nuv(): char_cands.append((s, MODE_NUV))
            elif s.is_char_nir(): char_cands.append((s, MODE_NIR))
        char_cands = [(s, m) for s, m in char_cands
                      if self.os.calc_intTime(s.star_num, m) <= self.intCutoff]
        if char_cands:
            best, mode = max(char_cands,
                             key=lambda sm: self.su.char_comp[sm[0].star_num, sm[1]] / self.os.calc_intTime(sm[0].star_num, sm[1]))
            return best, mode

        det_cands = [s for s in self.stars if self._det_eligible(s)]
        if det_cands:
            best = max(det_cands,
                       key=lambda s: self.su.det_comp[s.star_num] / self.os.calc_intTime(s.star_num))
            return best, -1
        # no targets
        return None, None

    def observation_detection(self, star):
        int_time = self.os.calc_intTime(star.star_num)
        t0 = self.tk.current_time
        self.tk.allocate(int_time)
        star.n_det += 1
        star.t_det_attempt = self.tk.current_time
        det_ok = bool(np.any(self._rng.random(size=(star.earths,)) < self.su.det_comp[star.star_num]))
        if star.is_unobserved():
            star.begin_obs()                        # unobserved -> observing
        if det_ok:
            star.n_det_ok += 1
            if star.t_det_first is None:
                star.t_det_first = t0
            star.t_det_last = t0
            if star.is_observing():
                star.first_det_success()            # observing -> orbit_det
        if star.is_observing() and star.detection_exhausted():
            star.give_up_obs()                      # observing -> retired (0 successes)
        if star.is_orbit_det() and star.orbit_det_exhausted():
            star.give_up_orbit_det()                # orbit_det -> retired (< 3 successes)
        star.find_orbit()                           # orbit_det -> char_vis if conditions met
        drm = {'star_num': star.star_num, 'mode': -1,
                         'success': det_ok, 't': t0,
                         'int_time': int_time}
        return drm

    def observation_characterization(self, star, mode):
        int_time = self.os.calc_intTime(star.star_num, mode)
        t0 = self.tk.current_time
        self.tk.allocate(int_time)
        star.n_char[mode] += 1
        char_ok = bool(np.any(self._rng.random(size=(star.earths,)) < self.su.char_comp[star.star_num, mode]))
        if char_ok:
            star.n_char_ok[mode] += 1
        if mode == MODE_VIS:
            star.advance_char_vis()
            star.retire_vis()
        elif mode == MODE_NUV:
            star.advance_char_nuv()
            star.retire_nuv()
        elif mode == MODE_NIR:
            star.succeed()
            star.retire_nir()
        drm = {'star_num': star.star_num, 'mode': mode,
                         'success': char_ok, 't': t0,
                         'int_time': int_time}
        return drm

    def observation_advance(self):
        active = [s for s in self.stars if not s.is_retired() and not s.is_success()]
        if not active:
            return False
        t0 = self.tk.current_time
        blocked = [s for s in active
                   if s.t_det_attempt is not None
                   and t0 - s.t_det_attempt < self.revisit_wait]
        if not blocked:
            return None
        next_open = min(s.t_det_attempt + self.revisit_wait for s in blocked)
        dt = next_open - t0
        self.tk.allocate(dt)
        drm = {'star_num': None, 'mode': None,
                         'success': True, 't': t0,
                         'int_time': dt}
        return drm

    def run_sim(self):
        n = self.su.n_star
        print(f"=== Star Observation Survey Simulation ({n} stars, eta={self.su.eta:.2f}) ===\n")

        while not self.tk.finished():
            # Bookkeeping
            # -- why here? initial state is the cause of the observation chosen
            self.state_history.append([s.state for s in self.stars])

            # 2/ get next target
            star, mode = self.next_target()

            # 3/ execute observation or time-advance
            if mode is None:
                drm = self.observation_advance()
                if not drm:
                    break # nothing more to do
            elif mode == -1:
                drm = self.observation_detection(star)
            elif mode >= 0:
                drm = self.observation_characterization(star, mode)
            else:
                raise RuntimeError('Bad mode')

            # Bookkeeping
            # -- why here? record action chosen
            self.DRM.append(drm)

        # End-of-mission sweep -- broadcast single trigger to all stars
        self._machine.dispatch('end_mission')
        self.state_history.append([s.state for s in self.stars])
        self._print_summary()

    def _print_summary(self):
        print(f"\n=== Final Summary "
              f"(mission time: {self.tk.current_time:.1f} / {self.tk.missionLife:.1f} days) ===")
        print(f"{'Star':>4}  {'dist':>5}  {'earths':>6}  {'n_det':>5}  {'n_det_ok':>8}  "
              f"{'nch_v':>5}  {'nch_n':>5}  {'nch_r':>5}  "
              f"{'nok_v':>5}  {'nok_n':>5}  {'nok_r':>5}  state")
        for s in self.stars:
            nc = s.n_char
            no = s.n_char_ok
            print(f"{s.star_num:4d}  {self.su.dist[s.star_num]:5.2f}  "
                  f"{s.earths:6d}  {s.n_det:5d}  {s.n_det_ok:8d}  "
                  f"{nc[0]:5d}  {nc[1]:5d}  {nc[2]:5d}  "
                  f"{no[0]:5d}  {no[1]:5d}  {no[2]:5d}  {s.state}")


def run_one():
    su = SimulatedUniverse(specs=specs)
    opt = OpticalSystem(su, specs)
    tk = TimeKeeping(specs)
    survey = SurveySimulation(su, opt, tk, specs)
    survey.run_sim()
    return survey


def main():
    run_one()


if __name__ == "__main__":
    main()
