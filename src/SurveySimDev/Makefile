
## Normalize the S input from a (possible) file/dir name -> script name
# 1: ensure S is simply-expanded variable, so it can be redefined
ifdef S
 # S_COPY serves as an indicator that S was supplied
 S_COPY:=$(S)
 override undefine S
 S:=$(S_COPY)
else
 S:=ScriptNotDefined
endif
# 2: remove some pathname components, if present
#    recall: the Scenario contains neither sims/... nor Scripts/...
# 2a: pull off Scripts/ if given as a file/dir (S=Scripts/foo.exp -> S=foo.exp)
S := $(patsubst Scripts/%,%,$(S))
# 2b: get script basename if given as a JSON (S=foo.json -> S=foo)
S := $(patsubst %.json,%,$(S))
# 2c: pull off leading sims/, if present (S=sims/foo -> S=foo)
S := $(patsubst sims/%,%,$(S))
# 2d: strip trailing / which could be present (S=sims/foo/ -> S=foo)
S := $(patsubst %/,%,$(S))
# 2e: strip added space at the end of S
S := $(strip $(S))
# 3: repeat script value back, if supplied
ifdef S_COPY
 $(info Make: Scenario name: "$(S)")
endif

trace: sims/$(S)/README.md

sims/$(S)/README.md: 
	uv run trace.py --output sims/$(S) Scripts/$(S).json
	touch $@

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


