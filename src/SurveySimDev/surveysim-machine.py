#!/usr/bin/env python
'''FSM state-machine diagram using NetworkX for node layout.

Produces a full-size annotated state-transition diagram from a specs JSON
file.  No simulation run is needed.

Run from src/SurveySimDev/:
    uv run surveysim-machine.py Scripts/specs-3band.json
'''

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from trace import FSMInfo  # local trace.py, not stdlib

ROOTDIR = Path('Media')
_SHADES = ['#111111', '#666666', '#aaaaaa']

# Figure/axis geometry -- must match subplots_adjust call in main().
_FIG_W, _FIG_H = 13.0, 7.5
_AX_L, _AX_R, _AX_B, _AX_T = 0.02, 0.98, 0.04, 0.93
_AX_W = _FIG_W * (_AX_R - _AX_L)   # physical axis width  (~12.48 in)
_AX_H = _FIG_H * (_AX_T - _AX_B)   # physical axis height (~6.68 in)
_D_MIN = 1.30   # min center-to-center in inch-scale data units (> any node box)
_DEEMPH_WEIGHT = 5.0  # edge weight for de-emphasized nodes (larger = weaker KK spring)
_DEEMPH_EDGE_COLOR = '#cccccc'
_DEEMPH_EDGE_LW = 0.8


def _edge_label(t):
    s = t['trigger']
    parts = list(t['conditions']) + ['not ' + c for c in t['unless']]
    if parts:
        s += '\n[' + ', '.join(parts) + ']'
    return s


def _scale_and_spread(pos_in, uniform=True):
    '''Scale positions into figure-inch units, then repel overlapping nodes.

    uniform=True  (KK):          preserve aspect ratio, fill 55% of axis.
    uniform=False (multipartite): stretch x and y independently to fill 85%,
                                  so layers and within-layer spacing both fill
                                  the figure without distorting either axis.
    '''
    nodes = list(pos_in.keys())
    arr = np.array([[pos_in[s][0], pos_in[s][1]] for s in nodes], dtype=float)
    arr -= arr.mean(axis=0)
    x_rng = float(arr[:, 0].max() - arr[:, 0].min()) or 1e-6
    y_rng = float(arr[:, 1].max() - arr[:, 1].min()) or 1e-6
    if uniform:
        scale = min(_AX_W * 0.55 / x_rng, _AX_H * 0.55 / y_rng)
        arr = arr * scale + np.array([_AX_W / 2, _AX_H / 2])
    else:
        arr[:, 0] = arr[:, 0] * (_AX_W * 0.85 / x_rng) + _AX_W / 2
        arr[:, 1] = arr[:, 1] * (_AX_H * 0.85 / y_rng) + _AX_H / 2
    pos = {s: arr[i].copy() for i, s in enumerate(nodes)}

    # Iterative pairwise repulsion: push any pair closer than _D_MIN apart.
    rng = np.random.default_rng(0)
    n = len(nodes)
    for _ in range(500):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = nodes[i], nodes[j]
                delta = pos[b] - pos[a]
                dist = float(np.linalg.norm(delta))
                if dist < _D_MIN:
                    moved = True
                    if dist < 1e-9:
                        delta = rng.standard_normal(2)
                        dist = float(np.linalg.norm(delta))
                    push = (_D_MIN - dist) / 2.0 * delta / dist
                    pos[a] -= push
                    pos[b] += push
        if not moved:
            break
    return {s: (float(v[0]), float(v[1])) for s, v in pos.items()}


def _build_graph(transitions_full, deemphasize=frozenset()):
    '''Build DiGraph for layout.

    Edges touching a de-emphasized node get weight _DEEMPH_WEIGHT; all others
    get weight 1.0.  KK uses weighted shortest-path distance as ideal spring
    length, so a high weight reduces that node's spring constants (k ~ 1/d^2)
    and pulls it toward the periphery without removing it from the layout.
    '''
    G = nx.DiGraph()
    for t in transitions_full:
        src, dst = t['src'], t['dst']
        w = (_DEEMPH_WEIGHT
             if (src in deemphasize or dst in deemphasize)
             else 1.0)
        G.add_edge(src, dst, weight=w)
    return G


def _multipartite_pos(G, initial):
    '''Assign longest-path-depth layers from initial state, return multipartite positions.

    Uses topological order to assign each node the length of the longest
    directed path from initial to that node.  Terminal sink nodes (retired,
    partial, etc.) therefore land in the rightmost column reachable from them,
    rather than the earliest column as with BFS shortest-path layering.
    Edge weights are ignored.
    '''
    depths = {n: -1 for n in G.nodes()}
    depths[initial] = 0
    for node in nx.topological_sort(G):
        if depths[node] < 0:
            continue
        for succ in G.successors(node):
            if depths[node] + 1 > depths[succ]:
                depths[succ] = depths[node] + 1
    max_d = max(depths.values())
    for node in G.nodes():
        G.nodes[node]['layer'] = depths[node] if depths[node] >= 0 else max_d + 1
    return nx.multipartite_layout(G, subset_key='layer', align='vertical')


def _assign_t_rads(transitions_full):
    '''Return per-transition curvature list; parallel edges get opposite signs.'''
    _BASE_RADS = [0.25, -0.25, 0.45, -0.45]
    groups = {}
    for i, t in enumerate(transitions_full):
        key = (t['src'], t['dst'])
        groups.setdefault(key, []).append(i)
    rads = [0.0] * len(transitions_full)
    for indices in groups.values():
        if len(indices) > 1:
            for k, idx in enumerate(indices):
                rads[idx] = _BASE_RADS[k % len(_BASE_RADS)]
    return rads


def _draw_machine(ax, fsm_info, t_rads, deemphasize=frozenset()):
    '''Draw the FSM on ax: edges with labels, then nodes.'''
    pos = fsm_info.state_pos
    src_count = {}

    for t, rad in zip(fsm_info.transitions_full, t_rads):
        src, dst = t['src'], t['dst']
        x0, y0 = pos[src]
        x1, y1 = pos[dst]

        if dst in deemphasize:
            color = _DEEMPH_EDGE_COLOR
            lw = _DEEMPH_EDGE_LW
            label_fs = 5
        else:
            n = src_count.get(src, 0)
            color = _SHADES[n % len(_SHADES)]
            src_count[src] = n + 1
            lw = 2.0
            label_fs = 6

        # Halve shrink for near-vertical arrows to match box half-height.
        s = 8 if abs(x0 - x1) < 0.05 * abs(y0 - y1) else 16
        ap = dict(arrowstyle='->', color=color, lw=lw, shrinkA=s, shrinkB=s)
        if rad:
            ap['connectionstyle'] = f'arc3,rad={rad}'
        ax.annotate('', xy=(x1, y1), xytext=(x0, y0), arrowprops=ap, zorder=1)

        # Label at arc midpoint, offset perpendicular to the edge.
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = x1 - x0, y1 - y0
        length = np.hypot(dx, dy)
        if length > 0:
            px, py = -dy / length, dx / length  # CCW perpendicular unit vector
        else:
            px, py = 0.0, 1.0
        # Arc visual midpoint is displaced ~0.5*rad*length in perp direction;
        # add a small extra gap to keep text off the arrow.
        sign = 1 if rad >= 0 else -1
        label_offset = 0.5 * rad * length + sign * 0.20
        lx = mx + label_offset * px
        ly = my + label_offset * py
        ax.text(lx, ly, _edge_label(t),
                ha='center', va='center', fontsize=label_fs,
                color=color, linespacing=1.3, zorder=2,
                bbox=dict(facecolor='white', edgecolor='none', pad=1))

    for state, (x, y) in pos.items():
        if state in deemphasize:
            text_color = _DEEMPH_EDGE_COLOR
            face = 'white'
            edge = _DEEMPH_EDGE_COLOR
            elw = _DEEMPH_EDGE_LW
        else:
            text_color = '#000'
            face = fsm_info.state_colors[state]
            edge = '#333'
            elw = 1.2
        ax.text(x, y, fsm_info.full_label[state],
                ha='center', va='center', fontsize=10, color=text_color, zorder=3,
                bbox=dict(boxstyle='round,pad=0.3',
                          facecolor=face, edgecolor=edge, linewidth=elw))

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) - 0.8, max(xs) + 0.8)
    ax.set_ylim(min(ys) - 0.8, max(ys) + 0.8)
    ax.axis('off')


def main():
    parser = argparse.ArgumentParser(
        description='State-machine diagram using NetworkX layout')
    parser.add_argument('--output', default=ROOTDIR, metavar='DIR', type=Path,
                        help='output directory (default: %(default)s)')
    parser.add_argument('--layout', choices=['multipartite', 'kk'], default='multipartite',
                        help='layout algorithm (default: %(default)s)')
    parser.add_argument('--deemphasize', default='', metavar='NODES',
                        help='comma-separated node names for visual de-emphasis; '
                             'also weakens KK springs when --layout kk')
    parser.add_argument('specs_file', metavar='SPECS',
                        help='simulation parameters (JSON format)')
    args = parser.parse_args()

    deemph = set(args.deemphasize.split(',')) - {''} if args.deemphasize else set()

    specs = json.loads(Path(args.specs_file).read_text())
    fsm_info = FSMInfo(specs)

    G = _build_graph(fsm_info.transitions_full, deemphasize=deemph)
    if args.layout == 'multipartite':
        raw_pos = _multipartite_pos(G, fsm_info.initial)
        fsm_info.state_pos = _scale_and_spread(raw_pos, uniform=False)
        title = 'State Machine -- NetworkX (Multipartite/BFS-Depth) Layout'
    else:
        raw_pos = nx.kamada_kawai_layout(G, weight='weight')
        fsm_info.state_pos = _scale_and_spread(raw_pos)
        title = 'State Machine -- NetworkX (Kamada-Kawai) Layout'

    t_rads = _assign_t_rads(fsm_info.transitions_full)

    fig, ax = plt.subplots(figsize=(13.0, 7.5))
    fig.subplots_adjust(top=0.93, bottom=0.04, left=0.02, right=0.98)
    _draw_machine(ax, fsm_info, t_rads, deemphasize=deemph)
    ax.set_title(title, fontsize=12, pad=8)

    args.output.mkdir(parents=True, exist_ok=True)
    save_path = args.output / 'machine-nx.png'
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f'Saved to {save_path}')


if __name__ == '__main__':
    main()
