# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SurveySimDev is a development area for SurveySimulation modules intended for eventual
use with EXOSIMS (Exoplanet Observation Simulation). 

## Context

Some of the modules and classes here
may implement methods analogous to those in either: 
`EXOSIMS.Prototypes.SurveySimulation` 
or
`EXOSIMS.SurveySimulation.coroOnlyScheduler`

(See here under the `ref/EXOSIMS` subdirectory.)

We are adopting a finite-state-machine (FSM) or state-transition, or StateCharts
approach for maintaining scheduler state. To do this, we have been using the 
`transitions` (also known as `pytransitions`)
Python package (`https://github.com/pytransitions/transitions`).


## Source Layout

All code under development lives under `src/SurveySimDev/`:

| File | Role |
|---|---|
| `trans.py` | Simulation core: classes, FSM wiring, main loop |
| `trace.py` | Visualization: four plot types saved to `Media/` |
| `__init__.py` | Empty package marker |

Plot outputs land in `src/SurveySimDev/Media/` (the `ROOTDIR` constant in `trace.py`).  
`trace.py` imports from `trans` with a bare `from trans import ...` -- it must be run from `src/SurveySimDev/`.

Historical snapshots of output images are archived under `Artifacts/state-trans-v0.{N}/`.

Reference EXOSIMS prototypes live under `ref/EXOSIMS/` (read-only reference; don't edit).

## Classes in `trans.py`

| Class | Purpose |
|---|---|
| `SimulatedUniverse` | Synthetic star catalog. Owns `det_comp[n_star]` and `char_comp[n_star, N_MODE]`. Init: `(*, specs)`. |
| `OpticalSystem` | `calc_intTime(star_num, mode=-1)` -- integration time in days. Init: `(SU, specs)`. |
| `TimeKeeping` | Accumulates mission elapsed time; `.finished()` when >= `specs['missionLife']`. Init: `(specs)`. |
| `StarInfo` | **FSM model**, one per star. Holds observation counters/timestamps and per-star parameters (`gap_required`, `n_det_remove`, `n_char_remove`). Implements condition methods and `on_enter_*` callbacks. Does NOT hold `det_comp` or `char_comp` -- those live on `SimulatedUniverse`. |
| `SpectralRetrieval` | Spectral analysis engine. Reads `specs['retrieval_models']`, a dict keyed by observing-state name (e.g. `'char_vis'`), each value being a per-QOI detection-probability dict. `spectral_retrieval(mode, obs_state, star_num, spectrum, snr)` returns `{'char_ok': bool, 'analysis': {...}}`. Init: `(optical_system, specs)`. |
| `SurveySimulation` | Orchestrator. Builds the `transitions.Machine`; accesses `su.det_comp`/`su.char_comp` directly. Init: `(time_keeping, sim_universe, optical_system, spectral_retrieval, specs)`. |

`run_one()` is the top-level convenience function (no arguments); returns a fully run `SurveySimulation`.

## FSM States and Transitions

This state list and list of legal state transitions is subject to change. At the moment, here
is the state breakdown, as an example of how it can look.

States (in order of progression):

```
unobserved -> observing -> orbit_det -> char_vis -> char_nuv -> char_nir -> success
```

Terminal / end-of-mission states: `retired`, `found`, `unknown`, `partial`.

Key triggers and their guard conditions (defined as methods on `StarInfo`):

| Trigger | Source -> Dest | Guards |
|---|---|---|
| `begin_obs` | unobserved -> observing | -- |
| `first_det_success` | observing -> orbit_det | -- |
| `give_up_obs` | observing -> retired | -- |
| `find_orbit` | orbit_det -> char_vis | `has_orbit` (>=3 successes), `has_sufficient_gap` (>=0.5 yr baseline) |
| `give_up_orbit_det` | orbit_det -> retired | -- |
| `advance_char_vis/nuv` | char_vis -> char_nuv, char_nuv -> char_nir | `vis/nuv_char_succeeded` |
| `retire_vis/nuv/nir` | char_X -> retired | `X_char_exhausted` (>=`n_char_remove` attempts, 0 successes) |
| `succeed` | char_nir -> success | `all_char_succeeded` |
| `end_mission` | observing/orbit_det/char_vis -> unknown/found/found; char_nuv/nir -> partial | `mission_ended` |

The `Machine` is built once in `SurveySimulation._build_machines()` with `ignore_invalid_triggers=True` and `auto_transitions=False`.  The end-of-mission sweep sets `star.end_of_mission = True` on all stars then calls `self._machine.dispatch('end_mission')`.

## DRM and State History

`SurveySimulation.DRM`: list of dicts, one per observation:
```python
{'star_num': int, 'mode': int,   # -1=det, 0/1/2=char VIS/NUV/NIR, None=time-advance
 'success': bool, 't': float,    # start time (days)
 'int_time': float}              # duration (days)
```

`SurveySimulation.state_history`: list of `n_star`-length state-name lists, snapshotted **before** each observation (so `state_history[k]` is the state vector that caused observation `k` to be chosen). A final snapshot is appended after the end-of-mission sweep.

## Observation Modes

- `mode == -1`: detection observation. Tries to detect any earth around the star. Success requires at least one earth passing the completeness draw.
- `mode in {0,1,2}` (VIS/NUV/NIR): characterization. Same probabilistic draw per `char_comp[mode]`.
- `mode is None`: time-advance entry in DRM (no real observation; plotted as a dashed line in trace).

## Scheduler Logic (`next_target`)

Priority: characterization candidates first (filtered by `specs['intCutoff']`), then detection candidates (filtered by `specs['revisit_wait']`).  Within each tier, pick by `comp / intTime` (greedy efficiency). Returns `(None, None)` when no target is available, which triggers `observation_advance()` to fast-forward time to the next revisit window.

## Visualization (`trace.py`)

The `FSMInfo` class (defined in `trace.py`) auto-derives all state-diagram properties
from `specs['state_transitions']` and `specs['state_initial']`: state list (BFS order),
2-row layout positions, per-state colors, full and abbreviated labels, dot styles per
observing mode, and arc radii for skip-edges (same-row transitions that span more than
one position unit, drawn as arcs to avoid overplotting).  All four plot functions accept
`(survey, fsm_info, ...)` and use these derived properties rather than any hardcoded constants.

Four plot functions, all called from `main()`:

| Function | Output file | Description |
|---|---|---|
| `make_trace_plot` | `trace.png` | Star x observation heatmap of states; dots for det/char obs |
| `make_transition_plot` | `transitions.png` | Per-star mini FSM diagrams showing visited states/transitions |
| `make_machine_doc_plot` | `machine.png` | Annotated full FSM + guard-condition docstring table |
| `make_strip_plot` | `strip.png` | Year-by-year timeline strips for Astro/Char/Det rows |


## specs dict (`trans.py`)

`specs` is a module-level dict that is the single source of truth for all
simulation parameters. It is passed as the last argument to every constructor.
All keys are lowercase, with the exception of `missionLife` and `intCutoff`.

| Key | Default | Description |
|---|---|---|
| `eta` | 0.4 | Mean number of earths per star (Poisson rate) |
| `missionLife` | 5*365.25 | Total mission duration (days) |
| `n_star` | 30 | Number of stars in the simulated catalog |
| `seed` | 0 | RNG seed; 0 means unseeded (truly random) |
| `n_det_remove` | 4 | Failed det attempts before retiring a star (0 successes) |
| `n_char_remove` | 2 | Char attempts per mode before retiring (0 successes) |
| `intCutoff` | 60.0 | Skip char observations longer than this (days) |
| `revisit_wait` | 0.3*365.25 | Min gap after any detection attempt (days) |
| `gap_required` | 0.5*365.25 | Min temporal baseline for orbit determination (days) |
| `obs_overhead` | 0.2 | Overhead added to every observation (days) |
| `char_overhead` | 0.8 | Additional overhead for characterizations (days) |
| `state_initial` | `{'*': 'unobserved'}` | Initial FSM state per star (`'*'` = all stars) |
| `state_transitions` | (list) | Full `pytransitions` transition spec; states are derived from this |
| `observingModes` | (list) | Per-mode dicts with keys: `instName`, `systName`, `tag`, `detection`, `lam`, `SNR`, `int_factor_x`, `comp_bound_x` |
| `retrieval_models` | (dict) | Keyed by observing-state name (e.g. `'char_vis'`); each value is a per-QOI detection-probability dict consumed by `SpectralRetrieval`. Omit or set to `{}` to defer all analysis. |

The `seed==0` convention applies in both `SimulatedUniverse` and `SurveySimulation`:
the value `0` is mapped to `None` before passing to `numpy.random.default_rng`.

## Guidance

All text files, including program files and markdown files, must have only ASCII text -- no unicode glyphs, including em-dashes.

