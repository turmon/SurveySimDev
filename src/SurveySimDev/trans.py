#!/usr/bin/env python
'''State-transition based scheduler demonstration
'''

import numpy as np
from transitions import Machine


############################################################
#
# --- Spectral retrieval parametric settings

# Purpose: basic multi-band retrieval
# concept: all are deferred: get the spectrum for later analysis
retrieval_models_defer = {
    'char_vis': {},
    'char_nir': {},
    'char_nuv': {},
}

# Purpose: multi-possibility Young et al. decision-tree retrieval
# concept: "analysis" is assignment of levels to constituents
# key is the *observing state* (which is unique)
retrieval_models_decision_tree = {
    'char_VIShi': {
        'H2O': {'no':0.1, 'yes': 0.6},
        'CH4': {'no':0.1, 'yes': 0.6},
        },
    'char_VISlo': {
        'O2':  {'no':0.2, 'medium':0.5, 'high': 0.8},
        },
    'char_NIR': {
        'CO2': {'no':0.3, 'yes': 0.7},
        'CH4': {'no':0.4, 'yes': 0.7},
        },
    'char_NUV': {
        'O3': {'no': 0.2, 'yes': 0.7},
        'pressure': {'low': 0.3, 'high': 0.8},
    }
}

############################################################
#
# --- ObservingModes
#
# Extras (non-physical, added just to run the sim):
#  int_factor_x: intTime multiplier per char mode (just for a mockup)
#  comp_bound_x: lower bound of completeness per mode (just for a mockup)

specs = {
    'eta':          0.4,             # mean number of earths per star
    'missionLife':  5 * 365.25,      # days -- total mission duration
    'n_star':       30,              # number of stars in the simulated catalog
    'seed':         0,               # RNG seed; 0 means unseeded (random)
    'n_det_remove': 4,               # failed det attempts before retiring a star
    'n_char_remove': 2,              # char attempts per mode before retiring
    'intCutoff':      60.0,            # days -- skip char observations longer than this
    'revisit_wait': 0.3 * 365.25,   # days -- min gap after any detection attempt
    'gap_required': 0.5 * 365.25,   # days -- min temporal baseline for orbit determination
    'obs_overhead':  0.2,            # days -- overhead added to every observation
    'char_overhead': 0.8,            # days -- additional overhead for characterizations
    'state_initial': {'*': 'unobserved'},
    'state_transitions': [
        # det-related
        {'trigger': 'process_det',   'source': 'unobserved', 'dest': 'observing', 'unless': 'det_exists'},
        {'trigger': 'process_det',   'source': 'unobserved', 'dest': 'orbit_det', 'conditions': 'det_exists'},
        {'trigger': 'process_det',   'source': 'observing',  'dest': 'retired',   'conditions': 'det_exhausted', 
                                                                                  'after': 'forget_star'},
        {'trigger': 'process_det',   'source': 'orbit_det',  'dest': 'char_vis',  'conditions': ['has_orbit_count',
                                                                                                 'has_orbit_span'],
                                                                                  'after': 'promote_star'},
        {'trigger': 'process_det',   'source': 'orbit_det',  'dest': 'retired',   'conditions': 'orbit_exhausted',
                                                                                  'after': 'forget_star'},
        # char-related
        {'trigger': 'process_char',  'source': 'char_vis',   'dest': 'char_nuv',  'conditions': 'char_exists'},
        {'trigger': 'process_char',  'source': 'char_vis',   'dest': 'retired',   'conditions': 'char_exhausted',
                                                                                  'after': 'forget_star'},
        {'trigger': 'process_char',  'source': 'char_nuv',   'dest': 'char_nir',  'conditions': 'char_exists'},
        {'trigger': 'process_char',  'source': 'char_nuv',   'dest': 'partial',   'conditions': 'char_exhausted',
                                                                                  'after': 'forget_star'},
        {'trigger': 'process_char',  'source': 'char_nir',   'dest': 'success',   'conditions': 'char_exists',
                                                                                  'after': 'forget_star'},
        {'trigger': 'process_char',  'source': 'char_nir',   'dest': 'partial',   'conditions': 'char_exhausted',
                                                                                  'after': 'forget_star'},

        # end-of-mission
        {'trigger': 'end_mission',   'source': ['char_nuv', 'char_nir'], 'dest': 'partial'},
        {'trigger': 'end_mission',   'source': ['orbit_det', 'char_vis'], 'dest': 'found'},
        {'trigger': 'end_mission',   'source': 'observing', 'dest': 'unknown'},
    ],
    'observingModes': [
        {
         'instName': 'imaging_BroadbandVisible_500',
         'systName': 'VVC500',
         'uses': [],
         'mode_num': -1,
         'int_factor_x': 1.0,
         'comp_bound_x': 0.1,
         'detection': True,
         'lam': 500,
         'SNR': 7,
         },
        {
         'instName': 'spectro910_R70_EMCCD',
         'systName': 'VVC575',
         'uses': ['char_vis'],
         'mode_num': 0,
         'int_factor_x': 1.2,
         'comp_bound_x': 0.8,
         'detection': False,
         'lam': 910,
         'SNR': 5.0,
         },
        {
         'instName': 'spectro_NUV310_EMCCD',
         'systName': 'VVC575',
         'uses': ['char_nuv'],
         'mode_num': 1,
         'int_factor_x': 1.0,
         'comp_bound_x': 0.9,
         'detection': False,
         'lam': 310,
         'SNR': 5.0
         },
        {
         'instName': 'spectro1500_R40_EMCCD',
         'systName': 'VVC575',
         'uses': ['char_nir'],
         'mode_num': 2,
         'int_factor_x': 2.0,
         'comp_bound_x': 0.5,
         'detection': False,
         'lam': 1500,
         'SNR': 8.5
         },
  ],
  'retrieval_models': retrieval_models_defer,
}


def _states_from_transitions(transitions):
    '''Derive the set of state names from a transitions list.'''
    states = set()
    for t in transitions:
        # add all named sources and destinations
        for endpoint in (t['source'], t['dest']):
            if isinstance(endpoint, list):
                states.update(endpoint)
            else:
                states.add(endpoint)
    return sorted(states)


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


class SimulatedUniverse:
    def __init__(self, *, specs):
        n_star = specs['n_star']
        seed = None if specs['seed'] == 0 else specs['seed']
        self.rng = np.random.default_rng(seed)
        self.eta = specs['eta']
        self.n_star = n_star
        self.earths = self.rng.poisson(self.eta, size=n_star)
        self.dist = self.rng.uniform(1.0, 10.0, size=n_star)
        # detection mode stuff
        self.det_mode = [om for om in specs['observingModes'] if om['detection']][0]
        det_raw = 5.0 / self.dist + self.rng.uniform(-0.1, 0.1, size=n_star)
        self.det_comp = np.clip(det_raw, self.det_mode['comp_bound_x'], 0.95)
        # char mode stuff
        # independent completeness per star and per char mode
        self.char_modes = [om for om in specs['observingModes'] if not om['detection']]
        char_raw = np.column_stack([self.rng.uniform(om['comp_bound_x'], 1.0, size=n_star)
                                    for om in self.char_modes])
        self.char_comp = np.clip(char_raw, 0.05, 1.0)


class OpticalSystem:
    def __init__(self, SU, specs):
        self._dist = SU.dist
        self.rng = SU.rng
        self.SimulatedUniverse = SU
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

    def compute_spectrum(self, mode, star_num):
        '''Return a (pseudo-)spectrum and corresponding SNR.

        Of course, this is a mock-up. But we use the spectral elements later
        to estimate atmospheric properties. The SNR is unused.'''
        spectrum = self.rng.uniform(0.0, 1.0, size=4)
        snr = 10.0 * np.ones_like(spectrum)
        return spectrum, snr


class SpectralRetrieval:
    def __init__(self, os, specs):
        self.OpticalSystem = os
        self.retrieval_models = specs.get('retrieval_models', {})

    def retrieval_deferred(self):
        analysis = {'all': 'deferred'}
        return dict(analysis=analysis)

    def retrieval_analysis(self, model, star, spectrum, snr):
        # Goal: produce analysis that says "CO2:high", etc.
        analysis = dict()
        for i, (qoi, levels) in enumerate(model.items()):
            # fictional construct: spectrum[0] pertains to qoi[0], etc.
            datum = spectrum[i]
            min_key = min(levels, key=lambda k: np.abs(datum - levels[k]))
            analysis[qoi] = min_key
        return dict(analysis=analysis)

    def null_retrieval(self, mode, obs_state, star_num):
        return {'char_ok': False}

    def spectral_retrieval(self, mode, obs_state, star_num, spectrum, snr):
        '''Return a dict of analysis of a star's received spectrum in a given mode.
        Dict keys:
           char_ok: bool, was the char successful
           analysis: dict of:
              qoi[str]: result[str]
        telling for each QOI (e.g., CH4), what was deduced from the spectrum.
        '''
        # (note that obs_state is also in the mode)
        spectral_model = self.retrieval_models.get(obs_state, {})
        if spectral_model:
            info = self.retrieval_analysis(spectral_model, star, spectrum, snr)
        else:
            info = self.retrieval_deferred()
        return {
            'char_ok': True,
            **info}


class StarInfo:
    n_mode = None
    def __init__(self, star_num, earths, gap_required, n_det_remove, n_char_remove):
        if not self.n_mode:
            RuntimeError('StarInfo needs its n_mode set')
        self.star_num = star_num
        self.earths = earths
        self.gap_required = gap_required
        # operational parameters (could be stored elsewhere)
        self.n_det_remove = n_det_remove
        self.n_char_remove = n_char_remove
        # scheduler state (updated over epochs)
        self.n_det = 0
        self.n_det_ok = 0
        self.n_char    = np.zeros(self.n_mode, dtype=int)
        self.n_char_ok = np.zeros(self.n_mode, dtype=int)
        self.retrievals = [dict() for i in range(self.n_mode)]
        self.t_det_first = None
        self.t_det_last = None
        self.t_det_attempt = None   # time of last detection attempt (success or failure)
        self.promoted = False  # allowed to make chars
        self.eligible = True  # eligible for new observations

    # --- predicates for "condition" and "unless" in transitions ---

    def det_exists(self, **kwargs):
        '''Detection succeeded at least once'''
        return self.n_det_ok > 0

    def det_exhausted(self, **kwargs):
        '''Planet detection failed: too many attempts'''
        return self.n_det >= self.n_det_remove

    def orbit_exhausted(self, **kwargs):
        '''Orbit determination failed: too many attempts'''
        # could potentially make this another parameter
        return (self.n_det - self.n_det_ok) >= self.n_det_remove

    def has_orbit_count(self):
        '''Enough points for orbit determination'''
        return self.n_det_ok >= 3

    def has_orbit_span(self):
        '''Orbit determination span criterion met'''
        if self.t_det_first is None or self.t_det_last is None:
            return False
        return (self.t_det_last - self.t_det_first) >= self.gap_required

    def char_exists(self, mode=None, retrieval=None):
        '''Characterization succeeded at least once'''
        return self.n_char_ok[mode] > 0

    def char_exhausted(self, mode=None, retrieval=None):
        '''Characterization limit was reached'''
        return self.n_char[mode] >= self.n_char_remove

    # --- callbacks that adjust star state

    def promote_star(self, **kwargs):
        self.promoted = True

    def forget_star(self, **kwargs):
        self.eligible = False

    # --- callbacks auto-discovered by transitions
    # --- (non-functional -- for logging only)
    # --- (using hard-coded names, conflicting with the spirit of genericity)

    def on_enter_observing(self, **kwargs):
        print(f"  Star {self.star_num:2d}: unobserved  -> OBSERVING")

    def on_enter_orbit_det(self, **kwargs):
        print(f"  Star {self.star_num:2d}: observing   -> ORBIT_DET      "
              f"(n_det_ok={self.n_det_ok}, t={self.t_det_first:.1f}d)")

    def on_enter_success(self, **kwargs):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: char_nir    -> SUCCESS        "
              f"(ok/att per mode: [{counts}])")

    def on_enter_partial(self, **kwargs):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: -> PARTIAL  (char ok/att=[{counts}])")

    def on_enter_found(self, **kwargs):
        print(f"  Star {self.star_num:2d}: -> FOUND    "
              f"(n_det_ok={self.n_det_ok}/{self.n_det})")

    def on_enter_unknown(self, **kwargs):
        print(f"  Star {self.star_num:2d}: -> UNKNOWN  "
              f"({self.n_det} det attempts, 0 successes)")

    def on_enter_retired(self, **kwargs):
        if np.any(self.n_char > 0):
            counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
            note = f"char ok/att=[{counts}]"
        else:
            note = f"never detected ({self.n_det} attempts)"
        print(f"  Star {self.star_num:2d}: -> RETIRED  ({note})")

    # --- FIXME: on_enter_char* are __especially__ not generic - generalize or delete
    def on_enter_char_vis(self, **kwargs):
        print(f"  Star {self.star_num:2d}: orbit_det   -> CHAR_VIS       "
              f"(earths={self.earths})")

    def on_enter_char_nuv(self, **kwargs):
        print(f"  Star {self.star_num:2d}: char_vis    -> CHAR_NUV       "
              f"(nok_vis={self.n_char_ok[0]})")

    def on_enter_char_nir(self, **kwargs):
        print(f"  Star {self.star_num:2d}: char_nuv    -> CHAR_NIR       "
              f"(nok_nuv={self.n_char_ok[1]})")


class SurveySimulation:
    def __init__(self, time_keeping, sim_universe, optical_system, spectral_retrieval, specs):
        self.tk = time_keeping
        self.su = sim_universe
        self.os = optical_system
        self.sr = spectral_retrieval
        self.revisit_wait  = specs['revisit_wait']
        self.gap_required  = specs['gap_required']
        self.intCutoff       = specs['intCutoff']
        self.n_det_remove  = specs['n_det_remove']
        self.n_char_remove = specs['n_char_remove']
        self._specs = specs
        self.rng = sim_universe.rng
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
        if star.eligible == False:
            return False
        if star.promoted:
            return False
        # otherwise, we're in detection-allowed phase
        # now, we just filter by time
        if star.t_det_attempt is None:
            return True
        else:
            return self.tk.current_time - star.t_det_attempt >= self.revisit_wait

    def _char_eligible(self, star, mode):
        if star.eligible == False:
            return False
        if not star.promoted:
            return False
        # are we allowed to use the desired observing mode?
        if star.state not in self.os.char_modes[mode]['uses']:
            return False
        return True

    def next_target(self):
        char_cands = []
        for s in self.stars:
            for m in range(self.os.n_mode):
                if self._char_eligible(s, m):
                    if self.os.calc_intTime(s.star_num, m) <= self.intCutoff:
                        char_cands.append((s, m))
        if char_cands:
            # rank by C/t
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
        # perform integration
        t0 = self.tk.current_time
        int_time = self.os.calc_intTime(star.star_num)
        self.tk.allocate(int_time)
        det_ok = bool(np.any(self.rng.random(size=(star.earths,)) < self.su.det_comp[star.star_num]))
        # update state
        star.n_det += 1
        star.t_det_attempt = t0
        if det_ok:
            star.n_det_ok += 1
            if star.t_det_first is None:
                star.t_det_first = t0
            star.t_det_last = t0
        # change star's observing state if needed
        star.process_det()
        # return value
        drm = {'star_num': star.star_num, 'mode': -1,
                         'success': det_ok, 't': t0,
                         'int_time': int_time}
        return drm

    def observation_characterization(self, star, mode):
        # perform integration
        t0 = self.tk.current_time
        int_time = self.os.calc_intTime(star.star_num, mode)
        self.tk.allocate(int_time)
        char_ok = bool(np.any(self.rng.random(size=(star.earths,)) < self.su.char_comp[star.star_num, mode]))
        if char_ok:
            spectrum, snr = self.os.compute_spectrum(mode, star.star_num)
            retrieval = self.sr.spectral_retrieval(mode, star.state, star.star_num, spectrum, snr)
        else:
            retrieval = self.sr.null_retrieval(mode, star.state, star.star_num)
        # update star's internal state
        star.n_char[mode] += 1
        if char_ok:
            star.n_char_ok[mode] += 1
        star.retrievals[mode] = retrieval
        # make observing-state transition if needed
        star.process_char(mode=mode, retrieval=retrieval)
        # return value
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
        n_mode = self.os.n_mode
        mode_labels = []
        for m in range(n_mode):
            uses = self.os.char_modes[m].get('uses', [])
            lbl = uses[0].replace('char_', '') if uses else str(m)
            mode_labels.append(lbl)
        sep = '  '
        col_w = 5
        mode_w = n_mode * col_w + (n_mode - 1) * len(sep)
        lbl_row = sep.join(f'{lbl:>{col_w}}' for lbl in mode_labels)
        fixed0 = f"{'':>4}  {'':>5}  {'':>6}  {'':>5}  {'':>8}"
        fixed2 = f"{'Star':>4}  {'dist':>5}  {'earths':>6}  {'n_det':>5}  {'n_det_ok':>8}"
        print(f"\n=== Final Star Outcomes "
              f"(mission time: {self.tk.current_time:.1f} / {self.tk.missionLife:.1f} days) ===")
        print(f"{fixed0}  {'n_char':^{mode_w}}  {'n_char_ok':^{mode_w}}")
        print(f"{fixed2}  {lbl_row}  {lbl_row}  state")
        for s in self.stars:
            nc = s.n_char
            no = s.n_char_ok
            nc_row = sep.join(f'{nc[m]:{col_w}d}' for m in range(n_mode))
            no_row = sep.join(f'{no[m]:{col_w}d}' for m in range(n_mode))
            print(f"{s.star_num:4d}  {self.su.dist[s.star_num]:5.2f}  "
                  f"{s.earths:6d}  {s.n_det:5d}  {s.n_det_ok:8d}  "
                  f"{nc_row}  {no_row}  {s.state}")

def run_one():
    tk = TimeKeeping(specs)
    su = SimulatedUniverse(specs=specs)
    os = OpticalSystem(su, specs)
    sr = SpectralRetrieval(os, specs)
    survey = SurveySimulation(tk, su, os, sr, specs)
    survey.run_sim()
    return survey


def main():
    run_one()


if __name__ == "__main__":
    main()
