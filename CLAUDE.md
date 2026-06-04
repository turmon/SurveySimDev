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
| `Scripts/*.json5` | Specs files defining simulation parameters and FSM strategy |
| `__init__.py` | Empty package marker |

Plot outputs land in `src/SurveySimDev/Media/` (the `ROOTDIR` constant in `trace.py`).
`trace.py` imports from `trans` with a bare `from trans import ...` -- it must be run from `src/SurveySimDev/`.

Historical snapshots of output images are archived under `Artifacts/state-trans-v0.{N}/`.

Reference EXOSIMS prototypes live under `ref/EXOSIMS/` (read-only reference; don't edit).


## Classes in `trans.py`

| Class | Purpose |
|---|---|
| `StateProps` | Dataclass holding normalized per-state properties: `mode` (list of int), `terminal` (bool), `success` (int). |
| `SimulatedUniverse` | Synthetic star catalog. Owns `det_comp[n_star]` and `char_comp[n_star, N_MODE]`. Init: `(*, specs)`. |
| `OpticalSystem` | `calc_intTime(star_num, mode=-1)` -- integration time in days. Init: `(SU, specs)`. |
| `TimeKeeping` | Accumulates mission elapsed time; `.finished()` when >= `specs['missionLife']`. Init: `(specs)`. |
| `StarInfo` | **FSM model**, one per star. Holds observation counters/timestamps and per-star parameters (`gap_required`, `n_det_remove`, `n_char_remove`). Implements condition methods and `on_enter_*` callbacks. Does NOT hold `det_comp` or `char_comp` -- those live on `SimulatedUniverse`. |
| `SpectralRetrieval` | Spectral analysis engine. Reads `specs['retrieval_models']`, a dict keyed by `'QOIs_{mode}'`, each value being a per-QOI detection-probability dict. `spectral_retrieval(mode, obs_state, star_num, spectrum, snr)` returns `{'char_ok': bool, 'analysis': {...}}`. Init: `(optical_system, specs)`. |
| `SurveySimulation` | Orchestrator. Builds the `transitions.Machine`; accesses `su.det_comp`/`su.char_comp` directly. Holds `state_props` dict (state name -> `StateProps`). Init: `(time_keeping, sim_universe, optical_system, spectral_retrieval, specs)`. |

`run_one(specs)` is the top-level convenience function; returns a fully run `SurveySimulation`.

Attribute naming convention: class instances stored as attributes of a parent class use CamelCase
(e.g., `self.TimeKeeping`, `self.OpticalSystem`). When extracted into a local helper variable,
use double-capitals (e.g., `TK = self.TimeKeeping`, `OS = self.OpticalSystem`).


## FSM States and Transitions

The FSM strategy -- which states exist and how transitions between them are defined -- is
entirely encoded in the specs script file (see below).  Different scripts implement
different scheduling strategies.  The example given here, from `specs-3band.json5`, is a
linear three-band characterization sequence and is a good reference case.

States (in order of progression for `specs-3band.json5`):

```
unobserved -> observing -> orbit_det -> char_vis -> char_nuv -> char_nir -> success
```

Terminal / end-of-mission states: `retired`, `found`, `unknown`, `partial`.

Key triggers and their guard conditions (defined as methods on `StarInfo`):

| Trigger | Source -> Dest | Guards |
|---|---|---|
| `process_det` | unobserved -> observing | `unless det_exists` |
| `process_det` | unobserved/observing -> orbit_det | `det_exists` |
| `process_det` | observing -> retired | `det_exhausted` |
| `process_det` | orbit_det -> char_vis | `has_orbit_count`, `has_orbit_span` |
| `process_det` | orbit_det -> retired | `orbit_exhausted` |
| `process_char` | char_vis -> char_nuv | `char_exists` |
| `process_char` | char_vis -> retired | `char_exhausted` |
| `process_char` | char_nuv -> char_nir | `char_exists` |
| `process_char` | char_nuv/nir -> partial | `char_exhausted` |
| `process_char` | char_nir -> success | `char_exists` |
| `end_mission` | observing -> unknown | -- |
| `end_mission` | orbit_det/char_vis -> found | -- |
| `end_mission` | char_nuv/char_nir -> partial | -- |

The `Machine` is built once in `SurveySimulation._build_machines()` with
`ignore_invalid_triggers=True` and `auto_transitions=False`.  The end-of-mission sweep
calls `self._machine.dispatch('end_mission')` to broadcast the trigger to all stars.

The `specs-tree.json5` script implements a richer branching-tree strategy with 10+
characterization states and multiple success terminals (`archean`, `modern`, `proterozoic`,
`dead_rocky`) -- illustrating that the same simulation engine supports qualitatively
different scheduling strategies purely through the specs file.


## DRM and State History

`SurveySimulation.DRM`: list of dicts, one per observation:
```python
{'star_num': int, 'mode': int,   # -1=det, 0/1/2/...=char mode index, None=time-advance
 'success': bool, 't': float,    # start time (days)
 'int_time': float}              # duration (days)
```

`SurveySimulation.state_history`: list of `n_star`-length state-name lists, snapshotted
**before** each observation (so `state_history[k]` is the state vector that caused
observation `k` to be chosen). A final snapshot is appended after the end-of-mission sweep.


## Observation Modes

- `mode == -1`: detection observation. Tries to detect any earth around the star.
  Success requires at least one earth passing the completeness draw.
- `mode >= 0`: characterization, indexed into `OpticalSystem.char_modes`.
  Same probabilistic draw per `char_comp[star_num, mode]`.
- `mode is None`: time-advance entry in DRM (no real observation; plotted as a dashed line).


## Scheduler Logic (`next_target`)

Priority: characterization candidates first (filtered by `specs['intCutoff']`), then
detection candidates (filtered by `specs['revisit_wait']`).  Within each tier, pick by
`comp / intTime` (greedy efficiency).  Char mode for each candidate star is read directly
from `state_props[star.state].mode` (set in `state_properties` in the specs file).
Returns `(None, None)` when no target is available, which triggers `observation_advance()`
to fast-forward time to the next revisit window.


## Visualization (`trace.py`)

The `FSMInfo` class (defined in `trace.py`) auto-derives all state-diagram properties
from `specs['state_transitions']` and `specs['state_initial']`: state list (BFS order),
2-row layout positions, per-state colors, full and abbreviated labels, arc radii for
skip-edges, and `terminal_states` frozenset.  All four plot functions accept
`(survey, fsm_info, ...)` and use these derived properties rather than any hardcoded constants.

Four plot functions, all called from `main()`:

| Function | Output file | Description |
|---|---|---|
| `make_trace_plot` | `trace.png` | Star x observation heatmap of states; dots for det/char obs; side panel shows earth count and outcome markers |
| `make_transition_plot` | `transitions.png` | Per-star mini FSM diagrams showing visited states/transitions |
| `make_machine_doc_plot` | `machine.png` | Annotated full FSM + guard-condition docstring table |
| `make_strip_plot` | `strip.png` | Year-by-year timeline strips for Astro/Char/Det rows |

CLI options for both `trace.py` and `surveysim-machine.py`:
- `--layout {auto,depth,kk}`: FSM node layout algorithm (`auto` = hand-coded 2-row, `depth` = longest-path layering via NetworkX, `kk` = Kamada-Kawai)
- `--faint NODES`: comma-separated state names to render with gray de-emphasis in all diagrams

Side-panel outcome markers in `trace.png` (rightmost column, per star):
- Dark-green `+`: end state has `success == 1`
- Red `x`: end state has `success == 0` and star had earths
- Black `+`: end state has `success == -1` and star had earths


## Specs Script Files

Simulation parameters and the FSM scheduling strategy are encoded together in JSON5
files under `src/SurveySimDev/Scripts/`.  JSON5 allows `//` and `/* */` comments and
trailing commas.  Each `.json5` file has a canonical `.json` copy (stripped of comments)
for tools that require standard JSON.

Available scripts:

| File | Strategy |
|---|---|
| `specs-simple.json5` | Single-band VIS characterization |
| `specs-3band.json5` | Three serial bands: VIS -> NUV -> NIR |
| `specs-3band-unordered-v1.json5` | Three bands in any order (full 2^3 state decomposition) |
| `specs-3band-unordered-v2.json5` | Three bands in any order (compact count-based states) |
| `specs-tree.json5` | Branching decision-tree with 4 observing modes and named biosphere outcomes |

### Scalar parameters

All keys are lowercase, with the exception of `missionLife` and `intCutoff`.

| Key | Typical value | Description |
|---|---|---|
| `eta` | 0.4 | Mean number of earths per star (Poisson rate) |
| `one_planet` | false | If true, use Binomial(1, eta) instead of Poisson |
| `missionLife` | 1826.25 | Total mission duration (days) |
| `n_star` | 30 | Number of stars in the simulated catalog |
| `seed` | 0 | RNG seed; 0 means unseeded (truly random) |
| `n_det_remove` | 4 | Failed det attempts before retiring a star (0 successes) |
| `n_char_remove` | 2 | Char attempts per mode before retiring (0 successes) |
| `intCutoff` | 60.0 | Skip char observations longer than this (days) |
| `revisit_wait` | 109.575 | Min gap after any detection attempt (days) |
| `gap_required` | 182.625 | Min temporal baseline for orbit determination (days) |
| `obs_overhead` | 0.2 | Overhead added to every observation (days) |
| `char_overhead` | 0.8 | Additional overhead for characterizations (days) |

The `seed==0` convention applies in both `SimulatedUniverse` and `SurveySimulation`:
the value `0` is mapped to `None` before passing to `numpy.random.default_rng`.

### FSM structure keys

| Key | Description |
|---|---|
| `state_initial` | `{'*': 'state_name'}` -- initial FSM state for all stars |
| `state_transitions` | List of `pytransitions` transition dicts (trigger, source, dest, conditions, unless, after) |
| `state_properties` | Optional dict mapping state names to property overrides (see below) |

`state_properties` maps each FSM state to a `StateProps` record.  States not listed get
default values.  `SurveySimulation._normalize_state_props()` builds a complete lookup
covering every state that appears in `state_transitions`.

| Property | Default | Description |
|---|---|---|
| `mode` | `[]` | Observing mode index (int) or list of ints for this state; `-1` normalizes to `[]` |
| `terminal` | false | True for sink states that have no outgoing transitions |
| `success` | 0 | Outcome quality: `+1` = full success, `0` = neutral/failed, `-1` = partial success |

### Observing modes

`observingModes` is a list of dicts, one per instrument mode.  Keys:

| Key | Description |
|---|---|
| `instName` | Instrument name string |
| `systName` | Optical system name string |
| `mode_num` | Integer index; `-1` for the detection mode |
| `detection` | true for the detection mode, false for all char modes |
| `lam` | Central wavelength (nm) |
| `SNR` | Required signal-to-noise ratio |
| `int_factor_x` | Integration time multiplier relative to detection (char modes only) |
| `comp_bound_x` | Lower bound of completeness draw for this mode |

Detection mode (`detection: true`) is identified and stored separately; all others become
`char_modes[0], char_modes[1], ...` in the order they appear.

### Retrieval models

`retrieval_models` is a dict keyed by `'QOIs_{mode_num}'`, one entry per char mode.
Each value is a dict of QOI names to detection-probability levels, consumed by
`SpectralRetrieval`.  An empty dict `{}` defers retrieval (records spectrum for later
analysis).  Omit the key entirely to disable spectral retrieval.

Example (from `specs-tree.json5`, mode 0):
```json
"QOIs_0": {
  "H2O": {"no": 0.1, "yes": 0.6},
  "CH4": {"no": 0.1, "yes": 0.6}
}
```


## Guidance

All text files, including program files and markdown files, must have only ASCII text -- no unicode glyphs, including em-dashes.
