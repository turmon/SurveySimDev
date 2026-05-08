# Design analysis: JSON-driven state machine configuration

## Context

After several iterations of "tweak the state machine", the question is how much of
the FSM logic can be externalized to JSON so that topology changes don't require
touching `observation_detection` / `observation_characterization` / `run_sim`.

---

## What is already JSON-serializable

`transitions_spec` is already a plain list of dicts with string values. The `Machine`
constructor accepts exactly that format. Conditions are looked up by name on the model
at runtime, so externalized condition names still resolve. Zero transformation needed.

---

## The split in observation methods

Both observation methods do two separate things:

1. **Fixed bookkeeping** — update counters, sample outcomes. Coupled to `StarInfo`
   internals. Does NOT change when iterating on state machine topology.

2. **Trigger-firing sequence** — the ordered `star.trigger()` calls. Pure topology;
   can be config-driven.

### Detection trigger sequence

```json
"detection_sequence": [
    "begin_obs",
    {"trigger": "first_det_success", "when": "success"},
    "give_up_obs",
    "give_up_orbit_det",
    "find_orbit"
]
```

Note: the explicit Python state guards currently in `observation_detection`
(`if star.is_observing()`, etc.) are redundant with `ignore_invalid_triggers=True` —
the `source` fields in `transitions_spec` already gate them. They can be dropped when
moving to the config-driven loop.

### Char trigger sequences (list index = mode number)

```json
"char_sequences": [
    ["advance_char_vis", "retire_vis"],
    ["advance_char_nuv", "retire_nuv"],
    ["succeed",          "retire_nir"]
]
```

### Generic observation method bodies (trigger section only)

```python
# detection — replaces the five explicit star.trigger() calls
for spec in config['detection_sequence']:
    trigger = spec if isinstance(spec, str) else spec['trigger']
    if isinstance(spec, dict) and spec.get('when') == 'success' and not det_ok:
        continue
    getattr(star, trigger)()

# characterization — replaces the mode == MODE_VIS / MODE_NUV / MODE_NIR block
for trigger in config['char_sequences'][mode]:
    getattr(star, trigger)()
```

---

## Full config structure

```json
{
  "states": [
    "unobserved", "observing", "orbit_det",
    "char_vis", "char_nuv", "char_nir",
    "success", "partial", "found", "unknown", "retired"
  ],
  "initial": "unobserved",
  "transitions": [
    {"trigger": "begin_obs",         "source": "unobserved", "dest": "observing"},
    {"trigger": "first_det_success", "source": "observing",  "dest": "orbit_det"},
    {"trigger": "give_up_obs",       "source": "observing",  "dest": "retired"},
    {"trigger": "find_orbit",        "source": "orbit_det",  "dest": "char_vis",
     "conditions": ["has_orbit", "has_sufficient_gap"]},
    {"trigger": "give_up_orbit_det", "source": "orbit_det",  "dest": "retired"},
    {"trigger": "advance_char_vis",  "source": "char_vis",   "dest": "char_nuv",
     "conditions": "vis_char_succeeded"},
    {"trigger": "retire_vis",        "source": "char_vis",   "dest": "retired",
     "conditions": "vis_char_exhausted"},
    {"trigger": "advance_char_nuv",  "source": "char_nuv",   "dest": "char_nir",
     "conditions": "nuv_char_succeeded"},
    {"trigger": "retire_nuv",        "source": "char_nuv",   "dest": "retired",
     "conditions": "nuv_char_exhausted"},
    {"trigger": "succeed",           "source": "char_nir",   "dest": "success",
     "conditions": "all_char_succeeded"},
    {"trigger": "retire_nir",        "source": "char_nir",   "dest": "retired",
     "conditions": "nir_char_exhausted"},
    {"trigger": "end_mission", "source": ["char_nuv", "char_nir"], "dest": "partial",
     "conditions": ["mission_ended"]},
    {"trigger": "end_mission", "source": ["orbit_det", "char_vis"], "dest": "found",
     "conditions": ["mission_ended"]},
    {"trigger": "end_mission", "source": "observing", "dest": "unknown",
     "conditions": ["mission_ended"]}
  ],
  "detection_sequence": [
    "begin_obs",
    {"trigger": "first_det_success", "when": "success"},
    "give_up_obs",
    "give_up_orbit_det",
    "find_orbit"
  ],
  "char_sequences": [
    ["advance_char_vis", "retire_vis"],
    ["advance_char_nuv", "retire_nuv"],
    ["succeed",          "retire_nir"]
  ],
  "end_mission_trigger": "end_mission",
  "det_eligible_states": ["unobserved", "observing", "orbit_det"],
  "char_states":         ["char_vis", "char_nuv", "char_nir"]
}
```

---

## Additional places that become config-driven

**`_det_eligible`** currently hardcodes the state list:
```python
if star.state not in config['det_eligible_states']:
    return False
```

**`next_target`** char-candidate scan hardcodes `is_char_vis()` / `is_char_nuv()` / `is_char_nir()`.
With `char_states` in config (index = mode number):
```python
for mode, state in enumerate(config['char_states']):
    if star.state == state:
        char_cands.append((star, mode))
```

---

## What must stay in Python

| Item | Reason |
|------|---------|
| Condition method **bodies** (`has_orbit`, `detection_exhausted`, …) | Predicates over numeric state; need Python or an expression language. Referenced by name in JSON — adding a new one means adding a Python method, but nothing else changes. |
| Counter update logic | Fixed per observation type (`n_det`, `n_det_ok`, timestamps). Not topology. |
| `next_target` scoring | Priority formula, `MAX_INT_TIME` filter — scheduling policy. |
| `on_enter_*` callbacks | Print infrastructure. |

---

## Boundary rule

**JSON owns:** topology — states, transitions, trigger sequences, condition names (by
reference), eligible-state lists.

**Python owns:** condition predicate implementations, observation bookkeeping/physics,
scheduling logic.

**Consequence:** adding a new state requires editing only the JSON. New Python is
needed only when a new condition predicate is required.
