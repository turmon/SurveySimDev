

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


# code-gen

# mixin class for decision-tree predicates
TREE_PREDICATE_CODE=StarInfoTree.py
# list of their function names
TREE_PREDICATE_NAMES=sr_tree_predicates.txt

predicates:$(TREE_PREDICATE_CODE)

.PHONY: predicates

# programmatically generate predicates for the decision tree mixin
$(TREE_PREDICATE_CODE): $(TREE_PREDICATE_NAMES)
	python gen_predicates.py > StarInfoTree.py

$(TREE_PREDICATE_NAMES): Scripts/specs-tree.json
	jq -r '.state_transitions.[].conditions' < $< > $@


