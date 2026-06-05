# Survey Simulation Scheduling Strategies: v0.7

Simulation outputs for five scheduling strategies, each encoded as a
finite-state-machine specs file. Strategies range from a minimal single-band
case through an ordered multi-band sequence to an unordered variant and a
full branching decision tree.

## Scenarios

- [Simple one-band characterization](specs-simple/README.md) --
  Blind search and orbit determination followed by a single VIS-range char;
  the most minimal scheduling concept.

- [Three-band serial (ordered)](specs-3band/README.md) --
  VIS characterization must succeed before NUV, NUV before NIR;
  the baseline ordered multi-band case.

- [Three-band unordered, v1](specs-3band-unordered-v1/README.md) --
  VIS, NUV, and NIR chars can be done in any order; state space is the full
  2^3 decomposition tracking each band individually.

- [Three-band unordered, v2](specs-3band-unordered-v2/README.md) --
  Same unordered three-band strategy as v1 but with a compact count-based
  state encoding; illustrates an alternative FSM design for the same policy.

- [Decision tree (Young et al.)](specs-tree/README.md) --
  Branching sequence with depth 2-3; spectral results gate transitions, and
  terminal states are named biosphere outcomes (modern, archean, proterozoic,
  dead_rocky, ambiguous).
