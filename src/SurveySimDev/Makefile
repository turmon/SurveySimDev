

# Run line: Observing sequence only
simple-trans:
	uv run trans.py Scripts/specs-simple.json

# Run line: Observing sequence plus plots
simple-trace:
	uv run trace.py Scripts/specs-simple.json

# File conversion

%.json: %.json5
	uv run util/json5_to_json.py < $< > $@

%.json: %.jsonc
	uv run util/json5_to_json.py < $< > $@


# programmatically generate predicates for the decision tree mixin
tree-predicates:
	python gen_predicates.py > StarInfoTree.py
