# Scheduler Mockup: Source code

Test harness for encapsulation of state in a StarInfo class, and integration
of StarInfo instances with a state diagram.

## Code units

`trans.py` -- `uv run trans.py` -- Perform one survey simulation

`trace.py` -- `uv run trace.py` -- Perform one survey simulation, and plot the results (DRM, etc.)

## Remarks

TODO: `trace.py`: Plot titles in could be improved
[done]

TODO: `trace.py`: Guard conditions on edges in `machine.png` are coming out on top of vertices. Raise zorder of vertices. 
[done]

TODO: `trans.py`: need a vertex list. Arrange this to replace the "uses"
key in the observingMode dictionary. Main function of vertex list is to map
vertex to the observing mode(s) that it looks at. Yes, this will be a
*list* of observingMode numbers. >1 mode means parallel-in-time
observations with (a) integration time = max\_mode(Tint(mode)); (b)
completeness for finding char\_ok is the max of observing-mode
completenesses; 

TODO: The next\_target() scan should not loop over modes! It
should use the mode taken from the current observing
state of the star.

TODO: `trans.py`: Remove some of the debugging print()'s. A few are hyper-specific.
[done]

TODO: `trans.py`: Needs to allow for specs-controlled changes to StarInfo mixins. Similar to specs["modules"] now.

TODO: `trace.py`: Make a new version of `coroOnlyScheduler.py` with the features of `trace.py`. Do not overplan, try it YOLO-ish and fix the mess later.


