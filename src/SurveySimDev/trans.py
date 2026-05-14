#!/usr/bin/env python
'''State-transition based scheduler demonstration
'''

import argparse
import json
import numpy as np
from transitions import Machine
from StarInfoTree import StarInfoTreeMixin


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
        if specs.get('one_planet', False):
            self.earths = self.rng.binomial(1, self.eta, size=n_star)
        else:
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
        to mock-estimate atmospheric properties. The SNR is unused.'''
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

    def retrieval_analysis(self, model, star_num, spectrum, snr):
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
        spectral_model = self.retrieval_models.get(f"QOIs_{mode}", {})
        if spectral_model:
            info = self.retrieval_analysis(spectral_model, star_num, spectrum, snr)
        else:
            info = self.retrieval_deferred()
        return {
            'char_ok': True,
            **info}


class StarInfo(StarInfoTreeMixin):
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
        print(f"  Star {self.star_num:2d}: promoted")
        self.promoted = True

    def forget_star(self, **kwargs):
        # print(f"  Star {self.star_num:2d}: forgotten")
        self.eligible = False

    # --- callbacks auto-discovered by transitions
    # --- (non-functional -- for logging only)
    # --- Logging is in place for these states: success, partial, retired

    def on_enter_success(self, **kwargs):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: char_nir    -> SUCCESS        "
              f"(ok/att per mode: [{counts}])")

    def on_enter_partial(self, **kwargs):
        counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
        print(f"  Star {self.star_num:2d}: -> PARTIAL  (char ok/att=[{counts}])")

    def on_enter_retired(self, **kwargs):
        if np.any(self.n_char > 0):
            counts = ', '.join(f"{self.n_char_ok[m]}/{self.n_char[m]}" for m in range(self.n_mode))
            note = f"char ok/att=[{counts}]"
        else:
            note = f"never detected ({self.n_det} attempts)"
        print(f"  Star {self.star_num:2d}: -> RETIRED  ({note})")


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
        if star.star_num == 13 and star.promoted:
            pass
            # FIXME
            #print("BREAK in Eligible")
            #breakpoint()
        if star.state not in self.os.char_modes[mode]['uses']:
            return False
        return True

    def next_target(self):
        char_cands = []
        for s in self.stars:
            for m in range(self.os.n_mode):
                #print(f">> Try ({s.star_num}, {m})")
                if self._char_eligible(s, m):
                    print(f">> Elig ({s.star_num}, {m})")
                    if self.os.calc_intTime(s.star_num, m) <= self.intCutoff:
                        char_cands.append((s, m))
        # TODO print(f">> Got {len(char_cands)} chars")
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
            print(f"{star.star_num = } | {mode = }")
            print(retrieval)
        else:
            print("FAIL")
            retrieval = self.sr.null_retrieval(mode, star.state, star.star_num)
        # update star's internal state
        star.n_char[mode] += 1
        if char_ok:
            star.n_char_ok[mode] += 1
        star.retrievals[mode] = retrieval
        # update star's observing-state if needed
        star.process_char(mode=mode, retrieval=retrieval)
        # return value
        drm = {'star_num': star.star_num, 'mode': mode,
                         'success': char_ok, 't': t0,
                         'int_time': int_time}
        return drm

    def observation_advance(self):
        active = [s for s in self.stars if s.eligible]
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
            lbl = uses[0].replace('char_', '') if uses else f'M#{m}'
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

def run_one(specs):
    tk = TimeKeeping(specs)
    su = SimulatedUniverse(specs=specs)
    os = OpticalSystem(su, specs)
    sr = SpectralRetrieval(os, specs)
    survey = SurveySimulation(tk, su, os, sr, specs)
    survey.run_sim()
    return survey


def main():
    parser = argparse.ArgumentParser(description='Run survey simulation')
    parser.add_argument('--seed', type=int, default=None, metavar='SEED',
                        help='random seed (default: from specs, or 0)')
    parser.add_argument('specs_file', metavar='SPECS',
                        help='simulation parameters (JSON format)')
    args = parser.parse_args()
    with open(args.specs_file) as f:
        args.specs = json.load(f)
    if args.seed is not None:
        args.specs['seed'] = args.seed
    run_one(args.specs)


if __name__ == "__main__":
    main()
