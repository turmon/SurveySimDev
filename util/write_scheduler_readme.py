#!/usr/bin/env python
'''Generate README.md for a scheduler simulation run.

Reads the leading // comment block from the .json5 companion of the given
.json specs file and emits a Markdown README to stdout.

The first non-empty comment line becomes the top-level heading.
Remaining comment lines become the description body.
Four fixed image links for the standard plot outputs are appended.

See the Makefile for usage.

Usage (from src/SurveySimDev/):
    uv run util/write_scheduler_readme.py Scripts/specs-3band.json > sims/specs-3band/README.md
'''

import argparse
import json
import sys
from pathlib import Path


_IMAGE_LINKS = [
    '![State Machine](machine.png)',
    '![Observation Chart](trace.png)',
    '![Time-slice Chart](strip.png)',
    '![All State Transitions](transitions.png)',
]


def read_initial_comments(json5_path):
    '''Return stripped body text from the leading // line block.

    Reads lines until the first line that does not start with //.
    Strips the leading // and at most one space from each line.
    '''
    lines = []
    with open(json5_path) as f:
        for raw in f:
            text = raw.rstrip('\n')
            if not text.startswith('//'):
                break
            body = text[2:]
            if body.startswith(' '):
                body = body[1:]
            lines.append(body)
    return lines


def main():
    parser = argparse.ArgumentParser(
        description='Generate README.md from a scheduler specs file')
    parser.add_argument('specs_file', metavar='SPECS',
                        help='JSON specs file (e.g. Scripts/specs-3band.json)')
    args = parser.parse_args()

    json_path = Path(args.specs_file)
    json5_path = json_path.with_suffix('.json5')

    if not json5_path.exists():
        print(f'Error: {json5_path} not found', file=sys.stderr)
        sys.exit(1)

    comment_lines = read_initial_comments(json5_path)

    # Split into heading (first non-empty line) and body (the rest).
    heading = ''
    body_lines = []
    found_heading = False
    for line in comment_lines:
        if not found_heading:
            if line.strip():
                heading = line.strip()
                found_heading = True
        else:
            body_lines.append(line)

    # Drop trailing blank lines from body.
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    specs = json.loads(json_path.read_text())

    out = []
    out.append(f'# {heading}')
    out.append('')
    json5_name = json_path.with_suffix('.json5').name
    out.append(f'Script: [`{json_path}`]({json_path.name}) | [`json5`]({json5_name})')
    if body_lines:
        out.append('')
        out.extend(body_lines)
    out.append('')
    out.append('## Diagnostic Plots')
    for link in _IMAGE_LINKS:
        out.append('')
        out.append(link)
    out.append('')
    out.append('## State Properties')
    out.append('')
    out.append('```json')
    out.append(json.dumps(specs.get('state_properties', {}), indent=2))
    out.append('```')
    out.append('')
    out.append('## State Transitions')
    out.append('')
    out.append('```json')
    out.append(json.dumps(specs.get('state_transitions', []), indent=2))
    out.append('```')
    out.append('')

    sys.stdout.write('\n'.join(out))


if __name__ == '__main__':
    main()
