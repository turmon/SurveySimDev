import numpy as np
from transitions import Machine

MISSION_DURATION = 5 * 365.25   # days
MAX_DET = 3     # failed detection attempts before retiring an unobserved star
MAX_CHAR = 3    # characterization attempts per mode before retiring
REVISIT_WAIT = 0.3 * 365.25    # days — min gap after any detection attempt before re-observing
GAP_REQUIRED = 0.5 * 365.25    # days — min temporal baseline (t_det_last - t_det_first) for orbit

N_MODE = 3
MODE_VIS, MODE_NUV, MODE_NIR = 0, 1, 2
CHAR_INT_FACTORS = [1.2, 1.0, 1.5]   # intTime multiplier per char mode [vis, nuv, nir]
COMP_FACTORS     = [0.8, 0.9, 0.5]   # lower bound of char completeness per mode

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

    def is_partial_success(self):
        '''Some but not all char modes succeeded at mission end'''
        return bool(np.any(self.n_char_ok >= 1) and not np.all(self.n_char_ok >= 1))

    def detection_exhausted(self):
        '''No more det attempts allowed'''
        return self.n_det >= MAX_DET and self.n_det_ok == 0

    # --- state-entry callbacks auto-discovered by transitions ---

    def on_enter_detected(self):
        print(f"  Star {self.star_num:2d}: unobserved  -> DETECTED       "
              f"(n_det_ok={self.n_det_ok}, det_comp={self.det_comp:.2f}, "
              f"t={self.t_det_first:.1f}d)")

    def on_enter_orbit_found(self):
        print(f"  Star {self.star_num:2d}: detected    -> ORBIT_FOUND    "
              f"(n_det_ok={self.n_det_ok}, t={self.t_det_last:.1f}d)")

    def on_enter_promoted(self):
        print(f"  Star {self.star_num:2d}: orbit_found -> PROMOTED        "
              f"(earths={self.earths})")

    def on_enter_char_vis(self):
        print(f"  Star {self.star_num:2d}: promoted    -> CHAR_VIS")

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
            {'trigger': 'first_detection',   'source': 'unobserved',  'dest': 'detected'},
            {'trigger': 'give_up_detection', 'source': 'unobserved',  'dest': 'retired'},
            {'trigger': 'find_orbit',        'source': 'detected',    'dest': 'orbit_found',  'conditions': ['has_orbit', 'has_sufficient_gap']},
            {'trigger': 'promote',           'source': 'orbit_found', 'dest': 'promoted'},
            {'trigger': 'start_char',        'source': 'promoted',    'dest': 'char_vis'},
            {'trigger': 'advance_char_vis',  'source': 'char_vis',    'dest': 'char_nuv',     'conditions': 'vis_char_succeeded'},
            {'trigger': 'retire_vis',        'source': 'char_vis',    'dest': 'retired',      'conditions': 'vis_char_exhausted'},
            {'trigger': 'advance_char_nuv',  'source': 'char_nuv',    'dest': 'char_nir',     'conditions': 'nuv_char_succeeded'},
            {'trigger': 'retire_nuv',        'source': 'char_nuv',    'dest': 'retired',      'conditions': 'nuv_char_exhausted'},
            {'trigger': 'succeed',           'source': 'char_nir',    'dest': 'success',      'conditions': 'all_char_succeeded'},
            {'trigger': 'retire_nir',        'source': 'char_nir',    'dest': 'retired',      'conditions': 'nir_char_exhausted'},
            {'trigger': 'go_partial',        'source': ['char_vis', 'char_nuv', 'char_nir'], 'dest': 'partial', 'conditions': 'is_partial_success'},
        ]
        self._machine = Machine(
            model=self.stars,
            states=['unobserved', 'detected', 'orbit_found', 'promoted',
                    'char_vis', 'char_nuv', 'char_nir', 'success', 'partial', 'retired'],
            transitions=transitions_spec,
            initial='unobserved',
            ignore_invalid_triggers=True,
            auto_transitions=False,
        )

    def _det_eligible(self, star):
        if not (star.is_unobserved() or star.is_detected()):
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
        if char_cands:
            best, mode = max(char_cands,
                             key=lambda sm: sm[0].char_comp[sm[1]] / self.os.calc_intTime(sm[0].star_num, sm[1]))
            return best, mode

        det_cands = [s for s in self.stars if self._det_eligible(s)]
        if det_cands:
            best = max(det_cands,
                       key=lambda s: s.det_comp / self.os.calc_intTime(s.star_num))
            return best, -1

        return None, None

    def observation_detection(self, star):
        int_time = self.os.calc_intTime(star.star_num)
        self.tk.allocate(int_time)
        self.state_history.append([s.state for s in self.stars])
        star.n_det += 1
        star.t_det_attempt = self.tk.current_time
        det_ok = bool(np.any(self._rng.random(size=(star.earths,)) < star.det_comp))
        if det_ok:
            star.n_det_ok += 1
            if star.t_det_first is None:
                star.t_det_first = self.tk.current_time
            star.t_det_last = self.tk.current_time
            if star.is_unobserved():
                star.first_detection()
        if star.is_unobserved() and star.detection_exhausted():
            star.give_up_detection()
        star.find_orbit()
        self.DRM.append({'star_num': star.star_num, 'mode': -1,
                         'success': det_ok, 't': self.tk.current_time,
                         'int_time': int_time})

    def observation_characterization(self, star, mode):
        int_time = self.os.calc_intTime(star.star_num, mode)
        self.tk.allocate(int_time)
        self.state_history.append([s.state for s in self.stars])
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
        self.DRM.append({'star_num': star.star_num, 'mode': mode,
                         'success': char_ok, 't': self.tk.current_time,
                         'int_time': int_time})

    def observation_advance(self):
        active = [s for s in self.stars if not s.is_retired() and not s.is_success()]
        if not active:
            return False
        blocked = [s for s in active
                   if s.t_det_attempt is not None
                   and self.tk.current_time - s.t_det_attempt < REVISIT_WAIT]
        if not blocked:
            return False
        next_open = min(s.t_det_attempt + REVISIT_WAIT for s in blocked)
        self.tk.allocate(next_open - self.tk.current_time)
        return True

    def run_sim(self):
        n = self.su.n_star
        print(f"=== Star Observation Survey Simulation ({n} stars, eta={self.su.eta:.2f}) ===\n")

        while not self.tk.finished():
            # Step 1: resolve transient states
            for star in self.stars:
                if star.is_orbit_found():
                    star.promote()
                if star.is_promoted():
                    star.start_char()

            # Step 2: get next target
            star, mode = self.next_target()

            # Step 3: handle idle or execute observation
            if star is None:
                if not self.observation_advance():
                    break
                continue

            if mode == -1:
                self.observation_detection(star)
            elif mode >= 0:
                self.observation_characterization(star, mode)

        # End-of-mission: mark stars with partial char success
        for star in self.stars:
            star.go_partial()
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
