#!/usr/bin/env python
'''Make "trace" plots of Survey Simulations
'''

import argparse
from collections import deque
from pathlib import Path
import colorsys
import inspect

import json

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from trans import StarInfo, run_one

ROOTDIR = Path('Media')
_FAINT_COLOR = '#999999'
_FAINT_LW = 0.8


class FSMInfo:
    '''Pre-processed FSM metadata derived from a specs dict.

    Derives states, transitions, layout positions, colors, labels, and
    abbreviations from specs['state_transitions'] and specs['state_initial'].
    All attributes are plain dicts/lists that can be overridden after init.
    '''

    # Colors for main-chain states (indices 1..N in BFS order, before top-row terminal)
    _MAIN_COLORS = [
        '#9ecae1', '#3182bd', '#74c476', '#9e9ac8', '#fc8d59',
        '#e7969c', '#fdae6b', '#c7e9c0',
    ]
    # Colors for bottom-row terminal states, assigned by decreasing x position:
    # highest x = most-advanced outcome (light green), then yellow, gray, light blue
    _TERM_COLORS = ['#a1d99b', '#fec44f', '#969696', '#c6dbef', '#bcbddc']

    def __init__(self, specs):
        self.initial = (specs['state_initial'].get('*')
                        or next(iter(specs['state_initial'].values())))
        self.transitions_full = self._normalize_transitions(specs['state_transitions'])
        self.all_transitions = [(t['src'], t['dst']) for t in self.transitions_full]
        self.states = self._ordered_states()
        self.state_pos = self._auto_pos()
        self.state_colors = self._auto_colors()
        self.full_label = {s: self._auto_label(s) for s in self.states}
        self.abbrev = self._make_abbrev()
        self.dot_styles = self._auto_dot_styles(specs.get('observingModes', []))
        self.edge_rad = self._auto_edge_rad()
        self.edge_shade = self._auto_edge_shade()
        self.success_state = self._top_row_term  # may be None

    def _normalize_transitions(self, raw):
        result = []
        for t in raw:
            sources = t['source'] if isinstance(t['source'], list) else [t['source']]
            conds = t.get('conditions', [])
            if isinstance(conds, str):
                conds = [conds]
            unlesses = t.get('unless', [])
            if isinstance(unlesses, str):
                unlesses = [unlesses]
            for src in sources:
                result.append({
                    'src': src,
                    'dst': t['dest'],
                    'trigger': t['trigger'],
                    'conditions': list(conds),
                    'unless': list(unlesses),
                })
        return result

    def _ordered_states(self):
        all_states, srcs = set(), set()
        for t in self.transitions_full:
            all_states.update([t['src'], t['dst']])
            srcs.add(t['src'])
        terminal = all_states - srcs
        non_terminal = srcs

        # BFS from initial through non-terminal states
        ordered, seen = [], set()
        if self.initial in non_terminal:
            queue = deque([self.initial])
            seen.add(self.initial)
            while queue:
                s = queue.popleft()
                ordered.append(s)
                for t in self.transitions_full:
                    if t['src'] == s and t['dst'] in non_terminal and t['dst'] not in seen:
                        seen.add(t['dst'])
                        queue.append(t['dst'])
        for s in sorted(non_terminal - seen):
            ordered.append(s)

        # Top-row terminal: exactly one non-terminal predecessor = last BFS state
        last_nt = ordered[-1] if ordered else None
        self._top_row_term = None
        if last_nt:
            for s in sorted(terminal):
                nt_preds = {t['src'] for t in self.transitions_full
                            if t['dst'] == s and t['src'] in non_terminal}
                if nt_preds == {last_nt}:
                    self._top_row_term = s
                    break
        if self._top_row_term:
            ordered.append(self._top_row_term)

        self._n_top_row = len(ordered)
        ordered.extend(sorted(terminal - ({self._top_row_term} if self._top_row_term else set())))
        return ordered

    def _auto_pos(self):
        pos = {}
        for i, s in enumerate(self.states[:self._n_top_row]):
            pos[s] = (float(i), 1.2)
        bottom = self.states[self._n_top_row:]
        raw_x = {}
        for s in bottom:
            pred_xs = [pos[p][0]
                       for p in {t['src'] for t in self.transitions_full
                                 if t['dst'] == s and t['src'] in pos}]
            raw_x[s] = sum(pred_xs) / len(pred_xs) if pred_xs else 0.0
        # Spread bottom-row states to guarantee minimum 1-unit gap, preserving centroid.
        if len(bottom) > 1:
            order = sorted(bottom, key=lambda s: raw_x[s])
            xs = [raw_x[s] for s in order]
            for i in range(1, len(xs)):
                xs[i] = max(xs[i], xs[i - 1] + 1.0)
            orig_cx = sum(raw_x[s] for s in order) / len(order)
            shift = orig_cx - sum(xs) / len(xs)
            for s, x in zip(order, xs):
                raw_x[s] = x + shift
        for s in bottom:
            pos[s] = (raw_x[s], 0.0)
        return pos

    def _auto_colors(self):
        colors = {}
        top_row = self.states[:self._n_top_row]
        colors[top_row[0]] = '#f5f5f5'
        for i, s in enumerate(top_row[1:], 1):
            colors[s] = ('#006d2c' if s == self._top_row_term
                         else self._MAIN_COLORS[(i - 1) % len(self._MAIN_COLORS)])
        bottom = self.states[self._n_top_row:]
        for i, s in enumerate(sorted(bottom, key=lambda s: -self.state_pos[s][0])):
            colors[s] = self._TERM_COLORS[i % len(self._TERM_COLORS)]
        return colors

    @staticmethod
    def _auto_label(s):
        parts = s.split('_')
        if len(parts) == 1:
            return s
        return '\n'.join(p.upper() if len(p) <= 3 else p for p in parts)

    def _make_abbrev(self):
        raw = {}
        for s in self.states:
            stem = s[len('char_'):] if s.startswith('char_') else s
            raw[s] = stem[:3]
        count = {}
        for ab in raw.values():
            count[ab] = count.get(ab, 0) + 1
        seen, abbrev = {}, {}
        for s in self.states:
            ab = raw[s]
            if count[ab] > 1:
                n = seen.get(ab, 0)
                seen[ab] = n + 1
                abbrev[s] = ab[:2] + str(n)
            else:
                abbrev[s] = ab
        return abbrev

    def _auto_edge_rad(self):
        rads = {}
        for src, dst in self.all_transitions:
            x0, y0 = self.state_pos[src]
            x1, y1 = self.state_pos[dst]
            rads[(src, dst)] = (0.25 if y0 == y1 and abs(x1 - x0) > 1.05 else 0.0)
        return rads

    def _auto_edge_shade(self):
        _SHADES = ['#111111', '#666666', '#aaaaaa']
        shade = {}
        src_count = {}
        for src, dst in self.all_transitions:
            n = src_count.get(src, 0)
            shade[(src, dst)] = _SHADES[n % 3]
            src_count[src] = n + 1
        return shade

    def _auto_dot_styles(self, observing_modes):
        _CHAR_COLORS = ['#2ca02c', '#9e9ac8', '#fc8d59', '#e7ba52', '#6baed6']
        styles = {
            (-1, True):  ('#1f77b4', 'Det: Success'),
            (-1, False): ('black',   'Det: Fail'),
        }
        char_modes = [m for m in observing_modes if not m.get('detection', True)]
        for i, mode in enumerate(char_modes):
            m = mode['mode_num']
            color = _CHAR_COLORS[i % len(_CHAR_COLORS)]
            lam = mode.get('lam', '?')
            styles[(m, True)]  = (color, f'Char {lam}nm: Success')
            styles[(m, False)] = ('#d62728', f'Char {lam}nm: Fail')
        return styles


def make_trace_plot(survey, fsm_info, save_path=ROOTDIR/'trace.png'):
    n_star = survey.su.n_star
    DRM = survey.DRM
    n_obs = len(DRM)
    if n_obs == 0:
        print("No observations recorded.")
        return

    # Build integer state matrix (n_star x n_hist); n_hist = n_obs + 1
    n_hist = len(survey.state_history)
    state_idx = {s: i for i, s in enumerate(fsm_info.states)}
    num_matrix = np.array(
        [[state_idx[survey.state_history[k][i]] for k in range(n_hist)]
         for i in range(n_star)],
        dtype=float,
    )

    cmap = ListedColormap([fsm_info.state_colors[s] for s in fsm_info.states])

    # Figure size scales with data
    fig_w = max(14, n_obs * 0.08)
    fig_h = max(5, n_star * 0.28)
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = GridSpec(1, 2, width_ratios=[20, 1], wspace=0.04,
                  left=0.10, right=0.97, top=0.87, bottom=0.10)
    ax_main = fig.add_subplot(gs[0])
    ax_side = fig.add_subplot(gs[1])

    # --- Main panel: state background ---
    ax_main.imshow(
        num_matrix,
        aspect='auto',
        cmap=cmap,
        vmin=-0.5,
        vmax=len(fsm_info.states) - 0.5,
        origin='upper',
        interpolation='nearest',
    )

    # Observation dots; delay entries (mode=None) get a full-height tick instead
    for k, obs in enumerate(DRM):
        if obs['mode'] is None:
            ax_main.axvline(k, color='#888888', linewidth=0.6,
                            linestyle=':', alpha=0.7, zorder=2)
        else:
            color, _ = fsm_info.dot_styles.get(
                (obs['mode'], obs['success']),
                fsm_info.dot_styles.get((0, obs['success']), ('#999999', '')))
            ax_main.plot(
                k, obs['star_num'], 'o',
                color=color, markersize=4,
                markeredgewidth=0.3, markeredgecolor='white',
                zorder=3,
            )

    # Y-axis: star number + earth count
    earths = survey.su.earths
    ax_main.set_yticks(range(n_star))
    ax_main.set_yticklabels([f"{i} - ({earths[i]})" for i in range(n_star)], fontsize=7)
    ax_main.set_ylabel('Star Number - (Earth Count)')

    # Primary X-axis
    x_step = max(1, n_obs // 10)
    ax_main.set_xticks(range(0, n_obs, x_step))
    ax_main.set_xlabel('Observation number')

    # Secondary X-axis: mission time in years
    n_ticks = min(8, n_obs)
    tick_idx = np.linspace(0, n_obs - 1, n_ticks, dtype=int)
    ax2 = ax_main.twiny()
    ax2.set_xlim(ax_main.get_xlim())
    ax2.set_xticks(tick_idx)
    ax2.set_xticklabels([f"{DRM[k]['t'] / 365.25:.1f}" for k in tick_idx], fontsize=7)
    ax2.set_xlabel('Mission time (yr)', fontsize=9)

    ax_main.set_title('Survey Trace', pad=22)

    # Grid lines between rows
    ax_main.set_yticks([y - 0.5 for y in range(n_star + 1)], minor=True)
    ax_main.grid(axis='y', which='minor', color='white', linewidth=0.5, alpha=0.6)

    # Legend
    state_patches = [
        mpatches.Patch(facecolor=fsm_info.state_colors[s], edgecolor='#888',
                       linewidth=0.5, label=s.replace('_', ' '))
        for s in fsm_info.states
    ]
    dot_handles = [
        plt.Line2D([0], [0], marker='o', linestyle='none',
                   markerfacecolor=c, markeredgecolor='white',
                   markeredgewidth=0.3, markersize=5, label=lbl)
        for (_, __), (c, lbl) in fsm_info.dot_styles.items()
    ]
    ax_main.legend(
        handles=state_patches + dot_handles,
        loc='lower left', fontsize=7, ncol=2,
        framealpha=0.9, edgecolor='#ccc',
    )

    # --- Side panel: earths indicator ---
    for i in range(n_star):
        n = int(earths[i])
        if n > 0:
            sat = min(0.4 + 0.3 * (n - 1), 1.0)   # 0.4 -> 0.7 -> 1.0
            val = max(0.5, 0.9 - 0.2 * (n - 1))    # 0.9 -> 0.7 -> 0.5
            color = colorsys.hsv_to_rgb(1 / 3, sat, val)
            ax_side.add_patch(
                mpatches.Rectangle((0, i - 0.5), 1, 1,
                                   facecolor=color, edgecolor='none')
            )
            final = survey.stars[i].state
            if final == 'partial':
                ax_side.plot(0.5, i, 'P', color='black',
                             markersize=5, zorder=4)
            elif final != fsm_info.success_state:
                ax_side.plot(0.5, i, 'x', color='red',
                             markersize=7, markeredgewidth=1.5, zorder=4)

    ax_side.set_xlim(0, 1)
    ax_side.set_ylim(n_star - 0.5, -0.5)   # inverted to match imshow
    ax_side.set_xticks([])
    ax_side.set_yticks([])
    ax_side.set_xlabel('Earth', fontsize=12)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def _star_visits(survey, star_idx):
    """Return (visited_states, taken_transitions) for one star."""
    # state_history[-1] is the post-mission snapshot (includes partial)
    seq = [survey.state_history[k][star_idx] for k in range(len(survey.state_history))]
    visited = set(seq)
    taken = {(a, b) for a, b in zip(seq, seq[1:]) if a != b}
    return visited, taken


def _draw_fsm(ax, fsm_info, visited, taken, fontsize=7, shrink=8, mini=False, shade=False,
              faint=frozenset()):
    """Draw a state machine diagram; visited/taken control fill and arrow weight."""
    lw = 1.5 if mini else 2.0
    for src, dst in fsm_info.all_transitions:
        x0, y0 = fsm_info.state_pos[src]
        x1, y1 = fsm_info.state_pos[dst]
        is_taken = (src, dst) in taken
        is_faint = dst in faint
        # Purely vertical arrows: shrink only along the box's narrow (height) axis,
        # so halve the shrink to match box half-height rather than half-width.
        s = max(2, shrink // 2) if x0 == x1 else shrink
        if is_faint:
            color = _FAINT_COLOR
            edge_lw = _FAINT_LW
        elif is_taken and shade:
            color = fsm_info.edge_shade[(src, dst)]
            edge_lw = lw
        else:
            color = '#111' if is_taken else '#ddd'
            edge_lw = lw if is_taken else 0.7
        ap = dict(
            arrowstyle='->',
            color=color,
            lw=edge_lw,
            shrinkA=s, shrinkB=s,
        )
        rad = fsm_info.edge_rad[(src, dst)]
        if rad:
            ap['connectionstyle'] = f'arc3,rad={rad}'
        ax.annotate('', xy=(x1, y1), xytext=(x0, y0), arrowprops=ap, zorder=1)
    for state, (x, y) in fsm_info.state_pos.items():
        label = fsm_info.abbrev[state] if mini else fsm_info.full_label[state]
        is_visited = state in visited
        is_faint = state in faint
        ax.text(
            x, y, label,
            ha='center', va='center', fontsize=fontsize, zorder=4,
            color=_FAINT_COLOR if is_faint else 'black',
            bbox=dict(
                boxstyle='round,pad=0.3',
                facecolor='white' if is_faint else (fsm_info.state_colors[state] if is_visited else 'white'),
                edgecolor=_FAINT_COLOR if is_faint else ('#333' if is_visited else '#bbb'),
                linewidth=_FAINT_LW if is_faint else (1.2 if is_visited else 0.5),
            ),
        )
    xs = [p[0] for p in fsm_info.state_pos.values()]
    ys = [p[1] for p in fsm_info.state_pos.values()]
    ax.set_xlim(min(xs) - 0.6, max(xs) + 1.5)
    ax.set_ylim(min(ys) - 0.6, max(ys) + 1.2)
    ax.axis('off')


def make_transition_plot(survey, fsm_info, save_path=ROOTDIR/'transitions.png', faint=frozenset()):
    n_star = survey.su.n_star
    n_cols = 5
    n_rows = (n_star + n_cols - 1) // n_cols

    ys_fsm = [p[1] for p in fsm_info.state_pos.values()]
    full_h = max(6.0, (max(ys_fsm) - min(ys_fsm)) * 1.5)
    fig_h = full_h + n_rows * 2.5
    fig_w = max(13.0, n_cols * 2.2)
    fig = plt.figure(figsize=(fig_w, fig_h))

    gs = GridSpec(
        2, 1, figure=fig,
        height_ratios=[full_h, n_rows * 2.5],
        hspace=0.3,
        top=0.95, bottom=0.02, left=0.01, right=0.99,
    )

    # Full machine
    ax_full = fig.add_subplot(gs[0])
    _draw_fsm(ax_full, fsm_info, set(fsm_info.states), set(fsm_info.all_transitions),
              fontsize=9, shrink=14, mini=False, shade=True, faint=faint)
    ax_full.set_title('State Machine -- All Transitions', fontsize=12, pad=8)

    # Per-star grid
    gs_stars = GridSpecFromSubplotSpec(
        n_rows, n_cols, subplot_spec=gs[1], hspace=0.7, wspace=0.15,
    )
    for i in range(n_star):
        ax = fig.add_subplot(gs_stars[i // n_cols, i % n_cols])
        visited, taken = _star_visits(survey, i)
        _draw_fsm(ax, fsm_info, visited, taken, fontsize=5, shrink=4, mini=True, faint=faint)
        # there is plenty of room to leave the title long
        # final = fsm_info.abbrev[survey.stars[i].state]
        final = survey.stars[i].state
        ax.set_title(f'Star {i}\n[{final}]', fontsize=8, pad=1)

    for i in range(n_star, n_rows * n_cols):
        ax = fig.add_subplot(gs_stars[i // n_cols, i % n_cols])
        ax.axis('off')

    plt.savefig(save_path, dpi=400, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def _edge_label(t):
    s = t['trigger']
    parts = list(t['conditions']) + ['not ' + c for c in t['unless']]
    if parts:
        s += '\n[' + ', '.join(parts) + ']'
    return s


def make_machine_doc_plot(survey, fsm_info, save_path=ROOTDIR/'machine.png', faint=frozenset()):
    ys_fsm = [p[1] for p in fsm_info.state_pos.values()]
    fsm_h = max(5.0, (max(ys_fsm) - min(ys_fsm)) * 1.5)
    fig_w, fig_h = 13.0, fsm_h + 3.5
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = GridSpec(
        2, 1, figure=fig,
        height_ratios=[fsm_h, 2.5],
        hspace=0.25,
        top=0.93, bottom=0.04, left=0.02, right=0.98,
    )

    # --- Top panel: annotated machine diagram ---
    ax = fig.add_subplot(gs[0])
    _draw_fsm(ax, fsm_info, set(fsm_info.states), set(fsm_info.all_transitions),
              fontsize=10, shrink=16, mini=False, shade=True, faint=faint)
    ax.set_title('State Machine -- Triggers and Guard Conditions', fontsize=12, pad=8)

    horiz_idx = 0
    diag_idx = 0
    for t in fsm_info.transitions_full:
        x0, y0 = fsm_info.state_pos[t['src']]
        x1, y1 = fsm_info.state_pos[t['dst']]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        label = _edge_label(t)
        is_faint = t['dst'] in faint
        label_color = _FAINT_COLOR if is_faint else '#333'
        label_fs = 5 if is_faint else 6
        label_zorder = 2 if is_faint else 3
        if y0 == y1:
            # horizontal arrow; lift label to arc apex for curved (skip) edges
            rad = fsm_info.edge_rad[(t['src'], t['dst'])]
            arc_lift = 0.5 * rad * abs(x1 - x0)
            y_off = 0.14 + 0.10 * (horiz_idx % 2)
            horiz_idx += 1
            ax.text(mx, my + arc_lift + y_off, label,
                    ha='center', va='bottom', fontsize=label_fs,
                    color=label_color, linespacing=1.3, zorder=label_zorder,
                    bbox=dict(facecolor='white', edgecolor='none', pad=1, alpha=0.70))
        else:
            # diagonal arrow -- stagger across three rows to reduce overplotting
            y_off = 0.13 * (diag_idx % 3) - 0.13
            diag_idx += 1
            ax.text(mx + 0.08, my + y_off, label,
                    ha='left', va='center', fontsize=label_fs,
                    color=label_color, linespacing=1.3, zorder=label_zorder,
                    bbox=dict(facecolor='white', edgecolor='none', pad=1, alpha=0.70))

    # --- Bottom panel: guard-condition docstring table ---
    ax_doc = fig.add_subplot(gs[1])
    ax_doc.axis('off')

    cond_names = []
    seen = set()
    for t in fsm_info.transitions_full:
        for c in t['conditions'] + t['unless']:
            if c not in seen:
                cond_names.append(c)
                seen.add(c)

    col_w = max((len(n) for n in cond_names), default=0) + 2
    lines = ['Guard conditions\n' + '-' * 48]
    for name in cond_names:
        method = getattr(StarInfo, name, None)
        try:
            doc = next(iter((inspect.getdoc(method) or '').splitlines()), '') if method else ''
        except Exception:
            doc = f'No docstring found for {name}'
        lines.append(f'{name.ljust(col_w)}{doc}')

    ax_doc.text(0.02, 0.95, '\n'.join(lines),
                ha='left', va='top',
                fontfamily='monospace', fontsize=9,
                transform=ax_doc.transAxes)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def make_strip_plot(survey, fsm_info, save_path=ROOTDIR/'strip.png'):
    DRM = survey.DRM
    if not DRM:
        print("No observations recorded.")
        return

    YEAR = 365.25
    N_YEARS = max(1, round(survey._specs['missionLife'] / YEAR))
    ADVANCE_COLOR = '#cccccc'
    STRIP_H = 0.45

    fig, axes = plt.subplots(N_YEARS, 1, sharex=True, figsize=(14, 7))
    if N_YEARS == 1:
        axes = [axes]
    fig.subplots_adjust(hspace=0.08, left=0.10, right=0.97, top=0.95, bottom=0.08)

    det_label_idx  = 0   # counts det  observations for above/below alternation
    char_label_idx = 0   # counts char observations for above/below alternation

    for k, obs in enumerate(DRM):
        t_start = obs['t']
        t_end   = t_start + obs['int_time']
        t_mid   = (t_start + t_end) / 2

        # Bar color
        if obs['mode'] is None:
            color = ADVANCE_COLOR
        else:
            state = survey.state_history[k][obs['star_num']]
            color = fsm_info.state_colors[state]

        # Categorical y-position; label index for above/below alternation
        if obs['mode'] is None:
            y_cat = 0   # Advance
            label_idx = None
        elif obs['mode'] == -1:
            y_cat = 2   # Det
            label_idx = det_label_idx
            det_label_idx += 1
        else:
            y_cat = 1   # Char
            label_idx = char_label_idx
            char_label_idx += 1

        # Draw bar segment(s), splitting at year boundaries
        for yr in range(N_YEARS):
            yr_t0 = yr * YEAR
            yr_t1 = (yr + 1) * YEAR
            seg_start = max(t_start, yr_t0) - yr_t0
            seg_end   = min(t_end,   yr_t1) - yr_t0
            if seg_start >= seg_end:
                continue
            axes[yr].barh(y_cat, seg_end - seg_start, left=seg_start,
                          height=STRIP_H, color=color, alpha=0.7, edgecolor='none')

            # Success/fail dot -- only for non-delay entries, only in the year
            # containing the temporal midpoint of the full (un-clipped) bar
            if obs['mode'] is not None and yr_t0 <= t_mid < yr_t1:
                dot_color = '#2ca02c' if obs['success'] else '#d62728'
                axes[yr].plot(t_mid - yr_t0, y_cat, 'o',
                              color=dot_color, markersize=3.75, zorder=3,
                              markeredgecolor='black', markeredgewidth=0.5)
                # Star number: alternate above (even index) / below (odd index)
                above = (label_idx % 2 == 0)
                axes[yr].text(t_mid - yr_t0,
                              y_cat + (0.28 if above else -0.28),
                              str(obs['star_num']),
                              ha='center', va='bottom' if above else 'top',
                              fontsize=5, zorder=4)

    for i, ax in enumerate(axes):
        ax.set_yticks([0, 1, 2])
        ax.set_yticklabels(['Astro', 'Char', 'Det'])
        ax.set_ylabel(f'Year {i + 1}')
        ax.set_ylim(-0.5, 2.5)
        ax.grid(axis='x', linewidth=0.3, alpha=0.5)

    axes[0].set_xlim(0, YEAR)
    axes[-1].set_xlabel('Mission time [d]')

    # Legend on last panel, lower left
    state_patches = [
        mpatches.Patch(facecolor=fsm_info.state_colors[s], alpha=0.7, edgecolor='none',
                       label=s.replace('_', ' '))
        for s in fsm_info.states
    ]
    dot_handles = [
        plt.Line2D([0], [0], marker='o', linestyle='none',
                   color='#2ca02c', markersize=5, label='Success'),
        plt.Line2D([0], [0], marker='o', linestyle='none',
                   color='#d62728', markersize=5, label='Fail'),
    ]
    axes[-1].legend(handles=state_patches + dot_handles,
                    loc='lower left', fontsize=7, ncol=2,
                    framealpha=0.9, edgecolor='#ccc')

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def _multipartite_pos(G, initial):
    '''Assign longest-path-depth layers from initial state, return multipartite positions.'''
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


def _apply_nx_layout(fsm_info, layout):
    '''Replace fsm_info.state_pos and edge_rad with a NetworkX-computed layout.

    Positions are scaled to match _auto_pos coordinate range (x: 0..n_top_row-1,
    y: 0..1.2) so that _draw_fsm's fixed shrink values remain correctly calibrated.
    edge_rad is recomputed using bidirectional-arc logic: 0.25 when the reverse
    edge (dst, src) also exists (separates opposing arrows), 0.0 otherwise.
    '''
    G = nx.DiGraph()
    for t in fsm_info.transitions_full:
        G.add_edge(t['src'], t['dst'])

    if layout == 'multipartite':
        raw_pos = _multipartite_pos(G, fsm_info.initial)
        layer_counts = {}
        for node in G.nodes():
            layer_counts[G.nodes[node]['layer']] = layer_counts.get(G.nodes[node]['layer'], 0) + 1
        n_max = max(layer_counts.values())
        y_target = max(1.2, (n_max - 1) * 1.2)
    else:
        raw_pos = nx.kamada_kawai_layout(G)
        y_target = 1.2

    xs = [p[0] for p in raw_pos.values()]
    ys = [p[1] for p in raw_pos.values()]
    x_rng = max(xs) - min(xs) or 1.0
    y_rng = max(ys) - min(ys) or 1.0
    n_top = fsm_info._n_top_row
    x_scale = (n_top - 1) / x_rng
    y_scale = y_target / y_rng
    fsm_info.state_pos = {
        s: ((raw_pos[s][0] - min(xs)) * x_scale,
            (raw_pos[s][1] - min(ys)) * y_scale)
        for s in raw_pos
    }

    all_pairs = set(fsm_info.all_transitions)
    fsm_info.edge_rad = {
        (src, dst): (0.25 if (dst, src) in all_pairs else 0.0)
        for src, dst in all_pairs
    }


def simulate_and_plot(args):
    survey = run_one(args.specs)
    fsm = FSMInfo(survey._specs)
    if args.layout != 'auto':
        _apply_nx_layout(fsm, args.layout)
    faint = args.faint
    make_trace_plot(survey, fsm, save_path=args.output/'trace.png')
    make_transition_plot(survey, fsm, faint=faint, save_path=args.output/'transitions.png')
    make_machine_doc_plot(survey, fsm, faint=faint, save_path=args.output/'machine.png')
    make_strip_plot(survey, fsm, save_path=args.output/'strip.png')

def main():
    parser = argparse.ArgumentParser(description='Plot survey simulation traces')
    parser.add_argument('--seed', type=int, default=None, metavar='SEED',
                        help='random seed (default: from specs, or 0)')
    parser.add_argument('--layout', choices=['auto', 'multipartite', 'kk'],
                        default='auto',
                        help='FSM node layout (default: %(default)s; auto = hand-coded 2-row)')
    parser.add_argument('--faint', default='', metavar='NODES',
                        help='comma-separated node names to render faintly in FSM diagrams')
    parser.add_argument('--output', default=ROOTDIR, metavar='DIR', type=Path,
                        help='output directory (default: %(default)s)')
    parser.add_argument('specs_file', metavar='SPECS',
                        help='simulation parameters (JSON format)')
    args = parser.parse_args()
    with open(args.specs_file) as f:
        args.specs = json.load(f)
    if args.seed is not None:
        args.specs['seed'] = args.seed
    args.faint = set(args.faint.split(',')) - {''} if args.faint else set()
    args.output.mkdir(parents=True, exist_ok=True)
    simulate_and_plot(args)
    
if __name__ == '__main__':
    main()
