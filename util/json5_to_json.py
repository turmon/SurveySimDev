#!/usr/bin/env python
'''Convert JSON5 to standard JSON (reads stdin or -i FILE, writes stdout).'''

import argparse
import json
import sys

import json5


def main():
    parser = argparse.ArgumentParser(
        description='Convert JSON5 to standard JSON')
    parser.add_argument('-i', metavar='FILE',
                        help='input JSON5 file (default: stdin)')
    args = parser.parse_args()

    if args.i:
        with open(args.i) as f:
            data = json5.load(f)
    else:
        data = json5.load(sys.stdin)

    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
