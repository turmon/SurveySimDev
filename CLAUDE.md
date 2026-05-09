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
| `SimulatedUniverse` | Synthetic star catalog. Per-star: `earths` (Poisson), `dist` (uniform 1-10 pc), `det_comp`, `char_comp[N_MODE]`. |
| `OpticalSystem` | `calc_intTime(star_num, mode=-1)` -- integration time in days. mode=-1 is detection; 0/1/2 are VIS/NUV/NIR char. |
| `TimeKeeping` | Accumulates mission elapsed time; `.finished()` when >= `MISSION_DURATION` (5 yr). |
| `StarInfo` | **FSM model**, one per star. Holds all observation counters/timestamps, implements condition methods and `on_enter_*` callbacks auto-discovered by `transitions`. |
| `SurveySimulation` | Orchestrator. Builds the `transitions.Machine` over all `StarInfo` instances. Contains `next_target()`, `observation_detection()`, `observation_characterization()`, `observation_advance()`, and `run_sim()`. |

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
| `retire_vis/nuv/nir` | char_X -> retired | `X_char_exhausted` (>=MAX_CHAR attempts, 0 successes) |
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

Priority: characterization candidates first (filtered by `MAX_INT_TIME`), then detection candidates (filtered by `REVISIT_WAIT`).  Within each tier, pick by `comp / intTime` (greedy efficiency). Returns `(None, None)` when no target is available, which triggers `observation_advance()` to fast-forward time to the next revisit window.

## Visualization (`trace.py`)

Four plot functions, all called from `main()`:

| Function | Output file | Description |
|---|---|---|
| `make_trace_plot` | `trace.png` | Star x observation heatmap of states; dots for det/char obs |
| `make_transition_plot` | `transitions.png` | Per-star mini FSM diagrams showing visited states/transitions |
| `make_machine_doc_plot` | `machine.png` | Annotated full FSM + guard-condition docstring table |
| `make_strip_plot` | `strip.png` | Year-by-year timeline strips for Astro/Char/Det rows |


## Guidance

All text files, including program files and markdown files, must have only ASCII text -- no unicode glyphs, including em-dashes.

