import colorsys
import inspect

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from trans import StarInfo, run_one

STATES = ['unobserved', 'detected', 'orbit_found', 'promoted', 'characterizing', 'success', 'retired']

STATE_COLORS = {
    'unobserved':     '#f5f5f5',
    'detected':       '#9ecae1',
    'orbit_found':    '#3182bd',
    'promoted':       '#fec44f',
    'characterizing': '#74c476',
    'success':        '#006d2c',
    'retired':        '#969696',
}

DOT_STYLES = {
    (-1, False): ('black',   'Failed detection'),
    (-1, True):  ('#1f77b4', 'Successful detection'),
    ( 0, True):  ('#2ca02c', 'Successful characterization'),
    ( 0, False): ('#d62728', 'Failed characterization'),
}

# State machine diagram layout
_STATE_POS = {
    'unobserved':     (0.0, 1.0),
    'detected':       (1.0, 1.0),
    'orbit_found':    (2.0, 1.0),
    'promoted':       (3.0, 1.0),
    'characterizing': (4.0, 1.0),
    'success':        (5.0, 1.0),
    'retired':        (2.0, 0.0),
}

_TRANSITIONS_FULL = [
    {'src': 'unobserved',     'dst': 'detected',       'trigger': 'first_detection',   'conditions': []},
    {'src': 'unobserved',     'dst': 'retired',        'trigger': 'give_up_detection', 'conditions': []},
    {'src': 'detected',       'dst': 'orbit_found',    'trigger': 'find_orbit',        'conditions': ['has_orbit', 'has_sufficient_gap']},
    {'src': 'orbit_found',    'dst': 'promoted',       'trigger': 'promote',           'conditions': []},
    {'src': 'promoted',       'dst': 'characterizing', 'trigger': 'start_char',        'conditions': []},
    {'src': 'characterizing', 'dst': 'success',        'trigger': 'succeed',           'conditions': ['char_succeeded']},
    {'src': 'characterizing', 'dst': 'retired',        'trigger': 'retire',            'conditions': ['char_exhausted']},
]
_ALL_TRANSITIONS = [(t['src'], t['dst']) for t in _TRANSITIONS_FULL]

_FULL_LABEL = {
    'unobserved':     'unobserved',
    'detected':       'detected',
    'orbit_found':    'orbit\nfound',
    'promoted':       'promoted',
    'characterizing': 'charact-\nerizing',
    'success':        'success',
    'retired':        'retired',
}

_ABBREV = {
    'unobserved':     'un',
    'detected':       'de',
    'orbit_found':    'or',
    'promoted':       'pr',
    'characterizing': 'ch',
    'success':        'su',
    'retired':        're',
}


def make_trace_plot(survey, save_path='trace.png'):
    n_star = survey.su.n_star
    DRM = survey.DRM
    n_obs = len(DRM)
    if n_obs == 0:
        print("No observations recorded.")
        return

    # Build integer state matrix (n_star × n_obs)
    state_idx = {s: i for i, s in enumerate(STATES)}
    num_matrix = np.array(
        [[state_idx[survey.state_history[k][i]] for k in range(n_obs)]
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

    # Observation dots
    for k, obs in enumerate(DRM):
        color, _ = DOT_STYLES[(obs['mode'], obs['success'])]
        ax_main.plot(
            k, obs['star_num'], 'o',
            color=color, markersize=4,
            markeredgewidth=0.3, markeredgecolor='white',
            zorder=3,
        )

    # Y-axis: star number + earth count
    earths = survey.su.earths
    ax_main.set_yticks(range(n_star))
    ax_main.set_yticklabels([f"{i} (e={earths[i]})" for i in range(n_star)], fontsize=7)
    ax_main.set_ylabel('Star')

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
        loc='lower right', fontsize=7, ncol=2,
        framealpha=0.9, edgecolor='#ccc',
    )

    # --- Side panel: earths indicator ---
    for i in range(n_star):
        n = int(earths[i])
        if n > 0:
            sat = min(0.4 + 0.3 * (n - 1), 1.0)   # 0.4 → 0.7 → 1.0
            val = max(0.5, 0.9 - 0.2 * (n - 1))    # 0.9 → 0.7 → 0.5
            color = colorsys.hsv_to_rgb(1 / 3, sat, val)
            ax_side.add_patch(
                mpatches.Rectangle((0, i - 0.5), 1, 1,
                                   facecolor=color, edgecolor='none')
            )
            if survey.stars[i].state != 'success':
                ax_side.plot(0.5, i, 'x', color='red',
                             markersize=7, markeredgewidth=1.5, zorder=4)

    ax_side.set_xlim(0, 1)
    ax_side.set_ylim(n_star - 0.5, -0.5)   # inverted to match imshow
    ax_side.set_xticks([])
    ax_side.set_yticks([])
    ax_side.set_xlabel('♁', fontsize=12)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def _star_visits(survey, star_idx):
    """Return (visited_states, taken_transitions) for one star."""
    n_obs = len(survey.DRM)
    seq = [survey.state_history[k][star_idx] for k in range(n_obs)]
    seq.append(survey.stars[star_idx].state)
    visited = set(seq)
    taken = {(a, b) for a, b in zip(seq, seq[1:]) if a != b}
    # orbit_found and promoted are transient — not captured in state_history
    if 'detected' in visited and 'characterizing' in visited:
        visited |= {'orbit_found', 'promoted'}
        taken |= {('detected', 'orbit_found'), ('orbit_found', 'promoted'),
                  ('promoted', 'characterizing')}
    return visited, taken


def _draw_fsm(ax, visited, taken, fontsize=7, shrink=8, mini=False):
    """Draw a state machine diagram; visited/taken control fill and arrow weight."""
    for src, dst in _ALL_TRANSITIONS:
        x0, y0 = _STATE_POS[src]
        x1, y1 = _STATE_POS[dst]
        is_taken = (src, dst) in taken
        ax.annotate(
            '', xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(
                arrowstyle='->',
                color='#111' if is_taken else '#ddd',
                lw=2.0 if is_taken else 0.7,
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
    ax.set_xlim(-0.6, 5.6)
    ax.set_ylim(-0.6, 1.6)
    ax.axis('off')


def make_transition_plot(survey, save_path='transitions.png'):
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
    ax_full.set_title('State Machine — All Transitions', fontsize=12, pad=8)

    # Per-star grid
    gs_stars = GridSpecFromSubplotSpec(
        n_rows, n_cols, subplot_spec=gs[1], hspace=0.7, wspace=0.15,
    )
    for i in range(n_star):
        ax = fig.add_subplot(gs_stars[i // n_cols, i % n_cols])
        visited, taken = _star_visits(survey, i)
        _draw_fsm(ax, visited, taken, fontsize=5, shrink=5, mini=True)
        final = _ABBREV[survey.stars[i].state]
        ax.set_title(f'Star {i} [{final}]', fontsize=6, pad=1)

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


def make_machine_doc_plot(survey, save_path='machine.png'):
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
    ax.set_title('State Machine — Triggers and Guard Conditions', fontsize=12, pad=8)

    for t in _TRANSITIONS_FULL:
        x0, y0 = _STATE_POS[t['src']]
        x1, y1 = _STATE_POS[t['dst']]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        label = _edge_label(t)
        if y0 == y1:
            # horizontal arrow — label above
            ax.text(mx, my + 0.18, label,
                    ha='center', va='bottom', fontsize=7,
                    color='#333', linespacing=1.3,
                    bbox=dict(facecolor='white', edgecolor='none', pad=1))
        else:
            # diagonal arrow — label to the right of midpoint
            ax.text(mx + 0.08, my, label,
                    ha='left', va='center', fontsize=7,
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
    lines = ['Guard conditions\n' + '─' * 48]
    for name in cond_names:
        method = getattr(StarInfo, name, None)
        doc = (inspect.getdoc(method) or '').splitlines()[0] if method else ''
        lines.append(f'{name.ljust(col_w)}{doc}')

    ax_doc.text(0.02, 0.95, '\n'.join(lines),
                ha='left', va='top',
                fontfamily='monospace', fontsize=9,
                transform=ax_doc.transAxes)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def main():
    survey = run_one()
    make_trace_plot(survey)
    make_transition_plot(survey)
    make_machine_doc_plot(survey)


if __name__ == '__main__':
    main()
