#!/usr/bin/env python
'''Make "trace" plots of Survey Simulations
'''

from pathlib import Path
import colorsys
import inspect

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from trans import StarInfo, run_one

ROOTDIR = Path('Media')

STATES = ['unobserved', 'observing', 'orbit_det',
          'char_vis', 'char_nuv', 'char_nir', 'success', 'partial',
          'found', 'unknown', 'retired']

STATE_COLORS = {
    'unobserved': '#f5f5f5',
    'observing':  '#9ecae1',   # light blue
    'orbit_det':  '#3182bd',   # medium blue
    'char_vis':   '#74c476',   # green  (VIS)
    'char_nuv':   '#9e9ac8',   # purple (NUV)
    'char_nir':   '#fc8d59',   # orange (NIR)
    'success':    '#006d2c',
    'partial':    '#a1d99b',   # light green -- some modes succeeded
    'found':      '#fec44f',   # warm yellow -- detected, not fully characterised
    'unknown':    '#c6dbef',   # very light blue -- observed but no successful detection
    'retired':    '#969696',
}

DOT_STYLES = {
    (-1, True):  ('#1f77b4', 'Det: Success'),
    (-1, False): ('black',   'Det: Fail'),
    ( 0, True):  ('#2ca02c', 'Char: Success'),
    ( 0, False): ('#d62728', 'Char: Fail'),
}

# State machine diagram layout
_STATE_POS = {
    'unobserved': (0.0, 1.0),
    'observing':  (1.0, 1.0),
    'orbit_det':  (2.0, 1.0),
    'char_vis':   (3.0, 1.0),
    'char_nuv':   (4.0, 1.0),
    'char_nir':   (5.0, 1.0),
    'success':    (6.0, 1.0),
    'unknown':    (1.0, 0.0),
    'found':      (2.5, 0.0),
    'retired':    (4.0, 0.0),
    'partial':    (5.5, 0.0),
}

_TRANSITIONS_FULL = [
    {'src': 'unobserved', 'dst': 'observing',  'trigger': 'begin_obs',         'conditions': []},
    {'src': 'observing',  'dst': 'orbit_det',  'trigger': 'first_det_success', 'conditions': []},
    {'src': 'observing',  'dst': 'retired',    'trigger': 'give_up_obs',       'conditions': []},
    {'src': 'orbit_det',  'dst': 'char_vis',   'trigger': 'find_orbit',        'conditions': ['has_orbit', 'has_sufficient_gap']},
    {'src': 'orbit_det',  'dst': 'retired',    'trigger': 'give_up_orbit_det', 'conditions': []},
    {'src': 'char_vis',   'dst': 'char_nuv',   'trigger': 'advance_char_vis',  'conditions': ['vis_char_succeeded']},
    {'src': 'char_vis',   'dst': 'retired',    'trigger': 'retire_vis',        'conditions': ['vis_char_exhausted']},
    {'src': 'char_nuv',   'dst': 'char_nir',   'trigger': 'advance_char_nuv',  'conditions': ['nuv_char_succeeded']},
    {'src': 'char_nuv',   'dst': 'retired',    'trigger': 'retire_nuv',        'conditions': ['nuv_char_exhausted']},
    {'src': 'char_nir',   'dst': 'success',    'trigger': 'succeed',           'conditions': ['all_char_succeeded']},
    {'src': 'char_nir',   'dst': 'retired',    'trigger': 'retire_nir',        'conditions': ['nir_char_exhausted']},
    {'src': 'char_nuv',   'dst': 'partial',    'trigger': 'end_mission',       'conditions': []},
    {'src': 'char_nir',   'dst': 'partial',    'trigger': 'end_mission',       'conditions': []},
    {'src': 'orbit_det',  'dst': 'found',      'trigger': 'end_mission',       'conditions': []},
    {'src': 'char_vis',   'dst': 'found',      'trigger': 'end_mission',       'conditions': []},
    {'src': 'observing',  'dst': 'unknown',    'trigger': 'end_mission',       'conditions': []},
]
_ALL_TRANSITIONS = [(t['src'], t['dst']) for t in _TRANSITIONS_FULL]

_FULL_LABEL = {
    'unobserved': 'unobserved',
    'observing':  'observing',
    'orbit_det':  'orbit\ndet',
    'char_vis':   'char\nVIS',
    'char_nuv':   'char\nNUV',
    'char_nir':   'char\nNIR',
    'success':    'success',
    'partial':    'partial',
    'found':      'found',
    'unknown':    'unknown',
    'retired':    'retired',
}

_ABBREV = {
    'unobserved': 'un',
    'observing':  'ob',
    'orbit_det':  'od',
    'char_vis':   'cv',
    'char_nuv':   'cu',
    'char_nir':   'ci',
    'success':    'su',
    'partial':    'pa',
    'found':      'fo',
    'unknown':    'uk',
    'retired':    're',
}


def make_trace_plot(survey, save_path=ROOTDIR/'trace.png'):
    n_star = survey.su.n_star
    DRM = survey.DRM
    n_obs = len(DRM)
    if n_obs == 0:
        print("No observations recorded.")
        return

    # Build integer state matrix (n_star x n_hist); n_hist = n_obs + 1
    n_hist = len(survey.state_history)
    state_idx = {s: i for i, s in enumerate(STATES)}
    num_matrix = np.array(
        [[state_idx[survey.state_history[k][i]] for k in range(n_hist)]
         for i in range(n_star)],
        dtype=float,
    )

    cmap = ListedColormap([STATE_COLORS[s] for s in STATES])

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
        vmax=len(STATES) - 0.5,
        origin='upper',
        interpolation='nearest',
    )

    # Observation dots; delay entries (mode=None) get a full-height tick instead
    for k, obs in enumerate(DRM):
        if obs['mode'] is None:
            ax_main.axvline(k, color='#888888', linewidth=0.6,
                            linestyle=':', alpha=0.7, zorder=2)
        else:
            color, _ = DOT_STYLES.get((obs['mode'], obs['success']),
                                       DOT_STYLES[(0, obs['success'])])
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
        mpatches.Patch(facecolor=STATE_COLORS[s], edgecolor='#888',
                       linewidth=0.5, label=s.replace('_', ' '))
        for s in STATES
    ]
    dot_handles = [
        plt.Line2D([0], [0], marker='o', linestyle='none',
                   markerfacecolor=c, markeredgecolor='white',
                   markeredgewidth=0.3, markersize=5, label=lbl)
        for (_, __), (c, lbl) in DOT_STYLES.items()
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
            elif final != 'success':
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


def _draw_fsm(ax, visited, taken, fontsize=7, shrink=8, mini=False):
    """Draw a state machine diagram; visited/taken control fill and arrow weight."""
    lw = 1.5 if mini else 2.0
    for src, dst in _ALL_TRANSITIONS:
        x0, y0 = _STATE_POS[src]
        x1, y1 = _STATE_POS[dst]
        is_taken = (src, dst) in taken
        ax.annotate(
            '', xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(
                arrowstyle='->',
                color='#111' if is_taken else '#ddd',
                lw=lw if is_taken else 0.7,
                shrinkA=shrink, shrinkB=shrink,
            ),
            zorder=1,
        )
    for state, (x, y) in _STATE_POS.items():
        label = _ABBREV[state] if mini else _FULL_LABEL[state]
        is_visited = state in visited
        ax.text(
            x, y, label,
            ha='center', va='center', fontsize=fontsize, zorder=3,
            bbox=dict(
                boxstyle='round,pad=0.3',
                facecolor=STATE_COLORS[state] if is_visited else 'white',
                edgecolor='#333' if is_visited else '#bbb',
                linewidth=1.2 if is_visited else 0.5,
            ),
        )
    ax.set_xlim(-0.6, 7.0)
    ax.set_ylim(-0.6, 1.6)
    ax.axis('off')


def make_transition_plot(survey, save_path=ROOTDIR/'transitions.png'):
    n_star = survey.su.n_star
    n_cols = 6
    n_rows = (n_star + n_cols - 1) // n_cols

    fig_h = 4.0 + n_rows * 2.0
    fig_w = max(13.0, n_cols * 2.2)
    fig = plt.figure(figsize=(fig_w, fig_h))

    gs = GridSpec(
        2, 1, figure=fig,
        height_ratios=[4.0, n_rows * 2.0],
        hspace=0.3,
        top=0.95, bottom=0.02, left=0.01, right=0.99,
    )

    # Full machine
    ax_full = fig.add_subplot(gs[0])
    _draw_fsm(ax_full, set(STATES), set(_ALL_TRANSITIONS),
              fontsize=9, shrink=14, mini=False)
    ax_full.set_title('State Machine -- All Transitions', fontsize=12, pad=8)

    # Per-star grid
    gs_stars = GridSpecFromSubplotSpec(
        n_rows, n_cols, subplot_spec=gs[1], hspace=0.7, wspace=0.15,
    )
    for i in range(n_star):
        ax = fig.add_subplot(gs_stars[i // n_cols, i % n_cols])
        visited, taken = _star_visits(survey, i)
        _draw_fsm(ax, visited, taken, fontsize=5, shrink=4, mini=True)
        final = _ABBREV[survey.stars[i].state]
        ax.set_title(f'Star {i} [{final}]', fontsize=8, pad=1)

    for i in range(n_star, n_rows * n_cols):
        ax = fig.add_subplot(gs_stars[i // n_cols, i % n_cols])
        ax.axis('off')

    plt.savefig(save_path, dpi=400, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def _edge_label(t):
    s = t['trigger']
    if t['conditions']:
        s += '\n[' + ', '.join(t['conditions']) + ']'
    return s


def make_machine_doc_plot(survey, save_path=ROOTDIR/'machine.png'):
    fig_w, fig_h = 13.0, 7.5
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = GridSpec(
        2, 1, figure=fig,
        height_ratios=[5.0, 2.5],
        hspace=0.25,
        top=0.93, bottom=0.04, left=0.02, right=0.98,
    )

    # --- Top panel: annotated machine diagram ---
    ax = fig.add_subplot(gs[0])
    _draw_fsm(ax, set(STATES), set(_ALL_TRANSITIONS), fontsize=10, shrink=16, mini=False)
    ax.set_title('State Machine -- Triggers and Guard Conditions', fontsize=12, pad=8)

    horiz_idx = 0
    diag_idx = 0
    for t in _TRANSITIONS_FULL:
        x0, y0 = _STATE_POS[t['src']]
        x1, y1 = _STATE_POS[t['dst']]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        label = _edge_label(t)
        if y0 == y1:
            # horizontal arrow -- alternate between two y offsets so adjacent labels
            # land on different rows and are less likely to overprint each other
            y_off = 0.14 + 0.10 * (horiz_idx % 2)
            horiz_idx += 1
            ax.text(mx, my + y_off, label,
                    ha='center', va='bottom', fontsize=6,
                    color='#333', linespacing=1.3,
                    bbox=dict(facecolor='white', edgecolor='none', pad=1))
        else:
            # diagonal arrow -- all midpoints share y=0.5, so stagger across three
            # rows to reduce overplotting
            y_off = 0.13 * (diag_idx % 3) - 0.13
            diag_idx += 1
            ax.text(mx + 0.08, my + y_off, label,
                    ha='left', va='center', fontsize=6,
                    color='#333', linespacing=1.3,
                    bbox=dict(facecolor='white', edgecolor='none', pad=1))

    # --- Bottom panel: guard-condition docstring table ---
    ax_doc = fig.add_subplot(gs[1])
    ax_doc.axis('off')

    cond_names = []
    seen = set()
    for t in _TRANSITIONS_FULL:
        for c in t['conditions']:
            if c not in seen:
                cond_names.append(c)
                seen.add(c)

    col_w = max(len(n) for n in cond_names) + 2
    lines = ['Guard conditions\n' + '-' * 48]
    for name in cond_names:
        method = getattr(StarInfo, name, None)
        try:
            doc = next(iter((inspect.getdoc(method) or '').splitlines()), '') if method else ''
        except:
            doc = f'No docstring found for {name}'
        lines.append(f'{name.ljust(col_w)}{doc}')

    ax_doc.text(0.02, 0.95, '\n'.join(lines),
                ha='left', va='top',
                fontfamily='monospace', fontsize=9,
                transform=ax_doc.transAxes)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def make_strip_plot(survey, save_path=ROOTDIR/'strip.png'):
    DRM = survey.DRM
    if not DRM:
        print("No observations recorded.")
        return

    YEAR = 365.25
    N_YEARS = 5
    ADVANCE_COLOR = '#cccccc'
    STRIP_H = 0.45

    fig, axes = plt.subplots(N_YEARS, 1, sharex=True, figsize=(14, 7))
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
            color = STATE_COLORS[state]

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

    # Legend on Year 5 panel, lower left
    state_patches = [
        mpatches.Patch(facecolor=STATE_COLORS[s], alpha=0.7, edgecolor='none',
                       label=s.replace('_', ' '))
        for s in STATES
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


def main():
    survey = run_one()
    make_trace_plot(survey)
    make_transition_plot(survey)
    make_machine_doc_plot(survey)
    make_strip_plot(survey)


if __name__ == '__main__':
    main()
