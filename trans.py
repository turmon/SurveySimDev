import numpy as np
from transitions import Machine

MISSION_DURATION = 5 * 365.25  # days
MAX_DET = 3     # failed detection attempts before retiring an unobserved star
MAX_CHAR = 3    # characterization attempts before retiring a characterizing star


class SimulatedUniverse:
    def __init__(self, eta, n_star=30, seed=None):
        rng = np.random.default_rng(seed)
        self.eta = eta
        self.n_star = n_star
        self.earths = rng.poisson(eta, size=n_star)
        self.dist = rng.uniform(1.0, 10.0, size=n_star)
        det_raw = 5.0 / self.dist + rng.uniform(-0.1, 0.1, size=n_star)
        # stars with no earths cannot be detected
        self.det_comp = np.where(
            self.earths > 0,
            np.clip(det_raw, 0.05, 0.95),
            0.0,
        )
        char_raw = 3.0 / self.dist + rng.uniform(-0.1, 0.1, size=n_star)
        self.char_comp = np.clip(char_raw, 0.05, 0.95)


class OpticalSystem:
    def __init__(self, sim_universe):
        self._dist = sim_universe.dist

    def calc_intTime(self, star_num):
        return float(0.5 * self._dist[star_num] ** 2)


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
        self.char_comp = char_comp
        self.n_det = 0
        self.n_det_ok = 0
        self.n_char = 0
        self.n_char_ok = 0
        self.t_det_first = None
        self.t_det_last = None
        self.next_available = 0.0

    # --- condition methods called by transitions ---

    def has_orbit(self):
        return self.n_det_ok >= 3

    def char_done(self):
        return self.n_char_ok >= 1 or self.n_char >= MAX_CHAR

    def detection_exhausted(self):
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

    def on_enter_characterizing(self):
        print(f"  Star {self.star_num:2d}: promoted    -> CHARACTERIZING")

    def on_enter_retired(self):
        if self.n_char > 0:
            if self.n_char_ok > 0:
                note = f"char SUCCESS ({self.n_char_ok}/{self.n_char})"
            else:
                note = f"char FAILED (0/{self.n_char})"
        else:
            note = f"never detected ({self.n_det} attempts)"
        print(f"  Star {self.star_num:2d}: -> RETIRED  ({note})")


class SurveySimulation:
    def __init__(self, sim_universe, optical_system, time_keeping):
        self.su = sim_universe
        self.os = optical_system
        self.tk = time_keeping
        self._rng = np.random.default_rng()
        self.stars = [
            StarInfo(
                star_num=i,
                earths=int(sim_universe.earths[i]),
                det_comp=float(sim_universe.det_comp[i]),
                char_comp=float(sim_universe.char_comp[i]),
            )
            for i in range(sim_universe.n_star)
        ]
        self._build_machines()

    def _build_machines(self):
        transitions_spec = [
            {'trigger': 'first_detection',   'source': 'unobserved',     'dest': 'detected'},
            {'trigger': 'give_up_detection', 'source': 'unobserved',     'dest': 'retired'},
            {'trigger': 'find_orbit',        'source': 'detected',       'dest': 'orbit_found',    'conditions': 'has_orbit'},
            {'trigger': 'promote',           'source': 'orbit_found',    'dest': 'promoted'},
            {'trigger': 'start_char',        'source': 'promoted',       'dest': 'characterizing'},
            {'trigger': 'retire',            'source': 'characterizing', 'dest': 'retired',        'conditions': 'char_done'},
        ]
        self._machine = Machine(
            model=self.stars,
            states=['unobserved', 'detected', 'orbit_found', 'promoted', 'characterizing', 'retired'],
            transitions=transitions_spec,
            initial='unobserved',
            ignore_invalid_triggers=True,
            auto_transitions=False,
        )

    def run_sim(self):
        n = self.su.n_star
        print(f"=== Star Observation Survey Simulation ({n} stars, eta={self.su.eta:.2f}) ===\n")

        while not self.tk.finished():
            candidates = [s for s in self.stars if not s.is_retired()]
            if not candidates:
                break

            star = min(candidates, key=lambda s: s.next_available)
            int_time = self.os.calc_intTime(star.star_num)

            if star.is_unobserved():
                self.tk.allocate(int_time)
                star.next_available = self.tk.current_time
                star.n_det += 1
                if self._rng.random() < star.det_comp:
                    star.n_det_ok += 1
                    star.t_det_first = self.tk.current_time
                    star.t_det_last = self.tk.current_time
                    star.first_detection()
                if star.is_unobserved() and star.detection_exhausted():
                    star.give_up_detection()

            elif star.is_detected():
                self.tk.allocate(int_time)
                star.next_available = self.tk.current_time
                star.n_det += 1
                if self._rng.random() < star.det_comp:
                    star.n_det_ok += 1
                    star.t_det_last = self.tk.current_time
                star.find_orbit()

            elif star.is_orbit_found():
                # transient state: resolve immediately, no int_time charged
                star.promote()
                star.start_char()

            elif star.is_characterizing():
                self.tk.allocate(int_time)
                star.next_available = self.tk.current_time
                star.n_char += 1
                if self._rng.random() < star.char_comp:
                    star.n_char_ok += 1
                star.retire()

        self._print_summary()

    def _print_summary(self):
        print(f"\n=== Final Summary "
              f"(mission time: {self.tk.current_time:.1f} / {MISSION_DURATION:.1f} days) ===")
        print(f"{'Star':>4}  {'dist':>5}  {'earths':>6}  {'n_det':>5}  "
              f"{'n_det_ok':>8}  {'n_char':>6}  {'n_char_ok':>9}  state")
        for s in self.stars:
            print(f"{s.star_num:4d}  {self.su.dist[s.star_num]:5.2f}  "
                  f"{s.earths:6d}  {s.n_det:5d}  {s.n_det_ok:8d}  "
                  f"{s.n_char:6d}  {s.n_char_ok:9d}  {s.state}")


def main():
    su = SimulatedUniverse(eta=0.4)
    opt = OpticalSystem(su)
    tk = TimeKeeping()
    survey = SurveySimulation(su, opt, tk)
    survey.run_sim()


if __name__ == "__main__":
    main()
