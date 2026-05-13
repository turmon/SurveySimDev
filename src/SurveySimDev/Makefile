

# Run lines
simple-trans:
	uv run trans.py Scripts/specs-simple.json

simple-trace:
	uv run trace.py Scripts/specs-simple.json

# File conversion

%.json: %.json5
	uv run util/json5_to_json.py < $< > $@

%.json: %.jsonc
	uv run util/json5_to_json.py < $< > $@

