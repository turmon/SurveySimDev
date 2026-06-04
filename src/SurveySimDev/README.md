# Scheduler Mockup: Source code

Test harness for encapsulation of state in a StarInfo class, and integration
of StarInfo instances with a state diagram.

## Input scripts

There are several scripts in `Scripts/*.json5` (in JSON5, which allows comments) to serve
as input for the mock scheduler below.

## Code units

`trans.py` -- `uv run trans.py` -- Perform one survey simulation

`trace.py` -- `uv run trace.py` -- Perform one survey simulation, and plot the results (DRM, etc.)

## Makefile

The `Makefile` incorporates some execution idioms:

`make Scripts/script.json` -- Converts `Scripts/script.json5` into `Scripts/script.json` by stripping comments.

`make S=Scripts/script.json trace` -- Runs `trace.py` with input `script.json`, writing resulting graphics to `sims/script/*.png`

## Remarks

Observing modes in "specs" and `trans.py`: Vertex list maps each 
vertex to the observing mode(s) that it can looks at. Note, this is a 
*list* of observingMode numbers -- when in this state,
the scheduler can try any of these modes.

## Parallel Characterizations

Generically, "parallel modes" means parallel-in-time
observations with (a) integration time = max\_mode(Tint(mode)); (b)
completeness for finding char\_ok is the max of observing-mode
completenesses; (c) keepout is the intersection
of single-mode keepout (but see below -- same Starlight
Suppression implies same keepout modulo wavelength).

Who is responsible for doing the work? 
- Key: Do we make OpticalSystem responsible for knowing about 
integration time of parallel modes? Alternatively, could
we have an OpticalSystem mixin class that would over-ride
the integration time method? Or do we implement that in the 
scheduler? Would one way to do that
- Side issues. Other consumers of "ObservingMode" are 
Completeness, TargetList (for completeness filtering),
Observatory (for keepout, depending on 
StarlightSuppressionSystem, which I suppose would be the same).
Note: given that we don't actually use characterization 
completeness, the Completeness part may be moot.

Just encoding the information.
(A) Could encode in the list-of-modes at observing-state S. E.g., S could
contain a list-of-lists-of-modes, where each sub-list is a group of parallel
observing modes. At present, S contains a list-of-modes. 
(B) Encode in a list of "parallel mode" instruments (in `instName`) that point to 
the instruments that will be used. I don't think this would be sensible
because too much information (lambda, SNR) will be replicated in other
lists, also in the observingMode
(C) Encode in a new variant-type ObservingMode that points to
all the information for the other parallel modes. Then we would always be observing
in a given single mode, but sometimes that mode would be running in parallel.
(D) Encode a "parallel sub-mode" in a given mode M that points to another
observing mode. 

Recording what has been done. We typically have a list (length #observingModes)
to record status. 
Suppose we have modes:
M1, M2, M3 = (M1 || M2)
Can we reason about doing M1 alone, M2 alone, or M3 alone?
A parallel-char can be half-successful (M1 || M2 could have M1 ok but M2 fail).
How do you record this in such a list (and then make decisions later)?
For instance, in (B) above, we would end up needing to record a composite
success in char_ok[M3], and we're not equipped for that.

Summary: We need to understand problem constraints to make good 
design choices. I'm making too big a deal about the other consumers
of modes -- just take care of integration time.


## TODOs


TODO: `trans.py`: The next\_target() scan should not loop over modes. 
It should use the modes-allowed list taken from the current observing
state of the star.
[DONE]

TODO: Specs encoding: Vertex list set up to declare terminal nodes, but I think they could
be found automatically.

TODO: `trans.py`: Allow for specs-controlled changes to StarInfo mixins. Similar to specs["modules"] now.

TODO: `trans.py`: transitions.png does not show the last state transition correctly (on the diagram) if it's a faint state.

TODO: Make a new version of `coroOnlyScheduler.py` with the features of `trans.py`. Do not overplan, try it YOLO-ish and fix the mess later.


