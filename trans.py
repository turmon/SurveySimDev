import numpy as np
from transitions import Machine

MISSION_DURATION = 5 * 365.25   # days
MAX_DET = 4     # failed detection attempts before retiring an unobserved star
MAX_CHAR = 2    # characterization attempts per mode before retiring
REVISIT_WAIT = 0.3 * 365.25    # days — min gap after any detection attempt before re-observing
GAP_REQUIRED = 0.5 * 365.25    # days — min temporal baseline (t_det_last - t_det_first) for orbit

N_MODE = 3
MODE_VIS, MODE_NUV, MODE_NIR = 0, 1, 2
CHAR_INT_FACTORS = [1.2, 1.0, 2.0]   # intTime multiplier per char mode [vis, nuv, nir]
COMP_FACTORS     = [0.8, 0.9, 0.5]   # lower bound of char completeness per mode
MAX_INT_TIME     = 60.0               # days — char observations longer than this are skipped

OBS_OVERHEAD = 0.2 # days, for everything
CHAR_OVERHEAD = 0.8 # days, additional for chars

class SimulatedUniverse:
    def __init__(self, eta, n_star=30, seed=None):
        rng = np.random.default_rng(seed)
        self.eta = eta
        self.n_star = n_star
        self.earths = rng.poisson(eta, size=n_star)
        self.dist = rng.uniform(1.0, 10.0, size=n_star)
        det_raw = 5.0 / self.dist + rng.uniform(-0.1, 0.1, size=n_star)
        self.det_comp = np.clip(det_raw, 0.05, 0.95)
        # independent completeness per star and per char mode
        char_raw = np.column_stack([rng.uniform(COMP_FACTORS[m], 1.0, size=n_star)
                                    for m in range(N_MODE)])
        self.char_comp = np.clip(char_raw, 0.05, 1.0)


class OpticalSystem:
    def __init__(self, sim_universe):
        self._dist = sim_universe.dist

    def calc_intTime(self, star_num, mode=-1):
        t = 0.5 * self._dist[star_num] ** 2
        if mode >= 0:
            t *= CHAR_INT_FACTORS[mode]
            t += CHAR_OVERHEAD
        t += OBS_OVERHEAD
        return float(t)


class TimeKeeping:
    def __init__(self):
        self.total_time = 0.0

    def allocate(self, days):
        self.total_time += days

    def finished(self):
        return self.total_time >= MISSION_DURATION

    @property
    def current_time(self):
        return self.total_time


class StarInfo:
    def __init__(self, star_num, earths, det_comp, char_comp):
        self.star_num = star_num
        self.earths = earths
        self.det_comp = det_comp
        self.char_comp = char_comp              # 1-D array, length N_MODE
        self.n_det = 0
        self.n_det_ok = 0
        self.n_char    = np.zeros(N_MODE, dtype=int)
        self.n_char_ok = np.zeros(N_MODE, dtype=int)
        self.t_det_first = None
        self.t_det_last = None
        self.t_det_attempt = None   # time of last detection attempt (success or failure)
        self.end_of_mission = False

    # --- condition methods called by transitions ---

    def has_orbit(self):
        '''Enough points for orbit determination'''
        return self.n_det_ok >= 3

    def has_sufficient_gap(self):
        '''Orbit determination span criterion met'''
        if self.t_det_first is None or self.t_det_last is None:
            return False
        return (self.t_det_last - self.t_det_first) >= GAP_REQUIRED

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
        return self.n_char[MODE_VIS] >= MAX_CHAR and self.n_char_ok[MODE_VIS] == 0

    def nuv_char_exhausted(self):
        '''NUV attempts exhausted with no success'''
        return self.n_char[MODE_NUV] >= MAX_CHAR and self.n_char_ok[MODE_NUV] == 0

    def nir_char_exhausted(self):
        '''NIR attempts exhausted with no success'''
        return self.n_char[MODE_NIR] >= MAX_CHAR and self.n_char_ok[MODE_NIR] == 0

    def detection_exhausted(self):
        '''No more det attempts allowed (0 successes)'''
        return self.n_det >= MAX_DET and self.n_det_ok == 0

    def orbit_det_exhausted(self):
        '''Detection attempts exhausted without reaching orbit (3 successes)'''
        return self.n_det >= MAX_DET and not self.has_orbit()

    def mission_ended(self):
        '''End-of-mission flag set; enables terminal transitions'''
        return self.end_of_mission

    # --- state-entry callbacks auto-discovered by transitions ---

    def on_enter_observing(self):
        print(f"  Star {self.star_num:2d}: unobserved  -> OBSERVING      "
              f"(det_comp={self.det_comp:.2f})")

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
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(N_MODE))
        print(f"  Star {self.star_num:2d}: char_nir    -> SUCCESS        "
              f"(ok/att per mode: [{counts}])")

    def on_enter_partial(self):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(N_MODE))
        print(f"  Star {self.star_num:2d}: -> PARTIAL  (char ok/att=[{counts}])")

    def on_enter_found(self):
        print(f"  Star {self.star_num:2d}: -> FOUND    "
              f"(n_det_ok={self.n_det_ok}/{self.n_det})")

    def on_enter_unknown(self):
        print(f"  Star {self.star_num:2d}: -> UNKNOWN  "
              f"({self.n_det} det attempts, 0 successes)")

    def on_enter_retired(self):
        if np.any(self.n_char > 0):
            counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(N_MODE))
            note = f"char ok/att=[{counts}]"
        else:
            note = f"never detected ({self.n_det} attempts)"
        print(f"  Star {self.star_num:2d}: -> RETIRED  ({note})")


class SurveySimulation:
    def __init__(self, sim_universe, optical_system, time_keeping):
        self.su = sim_universe
        self.os = optical_system
        self.tk = time_keeping
        self._rng = np.random.default_rng()
        self.state_history = []   # one n_star state-vector per observation
        self.DRM = []             # one record per observation
        self.stars = [
            StarInfo(
                star_num=i,
                earths=int(sim_universe.earths[i]),
                det_comp=float(sim_universe.det_comp[i]),
                char_comp=sim_universe.char_comp[i],
            )
            for i in range(sim_universe.n_star)
        ]
        self._build_machines()

    def _build_machines(self):
        transitions_spec = [
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
            {'trigger': 'end_mission', 'source': ['char_nuv', 'char_nir'], 'dest': 'partial',
                'conditions': ['mission_ended']},
            {'trigger': 'end_mission', 'source': ['orbit_det', 'char_vis'], 'dest': 'found',
                'conditions': ['mission_ended']},
            {'trigger': 'end_mission', 'source': 'observing', 'dest': 'unknown',
                'conditions': ['mission_ended']},
        ]
        self._machine = Machine(
            model=self.stars,
            states=['unobserved', 'observing', 'orbit_det',
                    'char_vis', 'char_nuv', 'char_nir', 'success', 'partial',
                    'found', 'unknown', 'retired'],
            transitions=transitions_spec,
            initial='unobserved',
            ignore_invalid_triggers=True,
            auto_transitions=False,
        )

    def _det_eligible(self, star):
        if not (star.is_unobserved() or star.is_observing() or star.is_orbit_det()):
            return False
        if star.t_det_attempt is None:
            return True
        return self.tk.current_time - star.t_det_attempt >= REVISIT_WAIT

    def next_target(self):
        char_cands = []
        for s in self.stars:
            if   s.is_char_vis(): char_cands.append((s, MODE_VIS))
            elif s.is_char_nuv(): char_cands.append((s, MODE_NUV))
            elif s.is_char_nir(): char_cands.append((s, MODE_NIR))
        char_cands = [(s, m) for s, m in char_cands
                      if self.os.calc_intTime(s.star_num, m) <= MAX_INT_TIME]
        if char_cands:
            best, mode = max(char_cands,
                             key=lambda sm: sm[0].char_comp[sm[1]] / self.os.calc_intTime(sm[0].star_num, sm[1]))
            return best, mode

        det_cands = [s for s in self.stars if self._det_eligible(s)]
        if det_cands:
            best = max(det_cands,
                       key=lambda s: s.det_comp / self.os.calc_intTime(s.star_num))
            return best, -1
        # no targets
        return None, None

    def observation_detection(self, star):
        int_time = self.os.calc_intTime(star.star_num)
        t0 = self.tk.current_time
        self.tk.allocate(int_time)
        star.n_det += 1
        star.t_det_attempt = self.tk.current_time
        det_ok = bool(np.any(self._rng.random(size=(star.earths,)) < star.det_comp))
        if star.is_unobserved():
            star.begin_obs()                        # unobserved → observing
        if det_ok:
            star.n_det_ok += 1
            if star.t_det_first is None:
                star.t_det_first = t0
            star.t_det_last = t0
            if star.is_observing():
                star.first_det_success()            # observing → orbit_det
        if star.is_observing() and star.detection_exhausted():
            star.give_up_obs()                      # observing → retired (0 successes)
        if star.is_orbit_det() and star.orbit_det_exhausted():
            star.give_up_orbit_det()                # orbit_det → retired (< 3 successes)
        star.find_orbit()                           # orbit_det → char_vis if conditions met
        drm = {'star_num': star.star_num, 'mode': -1,
                         'success': det_ok, 't': t0,
                         'int_time': int_time}
        return drm

    def observation_characterization(self, star, mode):
        int_time = self.os.calc_intTime(star.star_num, mode)
        t0 = self.tk.current_time
        self.tk.allocate(int_time)
        star.n_char[mode] += 1
        char_ok = bool(np.any(self._rng.random(size=(star.earths,)) < star.char_comp[mode]))
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
                   and t0 - s.t_det_attempt < REVISIT_WAIT]
        if not blocked:
            return None
        next_open = min(s.t_det_attempt + REVISIT_WAIT for s in blocked)
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

        # End-of-mission sweep — set flag then broadcast single trigger
        for star in self.stars:
            star.end_of_mission = True
        self._machine.dispatch('end_mission')
        self.state_history.append([s.state for s in self.stars])
        self._print_summary()

    def _print_summary(self):
        print(f"\n=== Final Summary "
              f"(mission time: {self.tk.current_time:.1f} / {MISSION_DURATION:.1f} days) ===")
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
    su = SimulatedUniverse(eta=0.4)
    opt = OpticalSystem(su)
    tk = TimeKeeping()
    survey = SurveySimulation(su, opt, tk)
    survey.run_sim()
    return survey


def main():
    run_one()


if __name__ == "__main__":
    main()
