import colorsys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec

from trans import OpticalSystem, SimulatedUniverse, SurveySimulation, TimeKeeping

STATES = ['unobserved', 'detected', 'orbit_found', 'promoted', 'characterizing', 'retired']

STATE_COLORS = {
    'unobserved':     '#f5f5f5',
    'detected':       '#9ecae1',
    'orbit_found':    '#3182bd',
    'promoted':       '#fec44f',
    'characterizing': '#74c476',
    'retired':        '#969696',
}

DOT_STYLES = {
    (-1, False): ('black',   'Failed detection'),
    (-1, True):  ('#1f77b4', 'Successful detection'),
    ( 0, True):  ('#2ca02c', 'Successful characterization'),
    ( 0, False): ('#d62728', 'Failed characterization'),
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

    ax_side.set_xlim(0, 1)
    ax_side.set_ylim(n_star - 0.5, -0.5)   # inverted to match imshow
    ax_side.set_xticks([])
    ax_side.set_yticks([])
    ax_side.set_xlabel('♁', fontsize=12)

    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved to {save_path}")


def main():
    su = SimulatedUniverse(eta=0.4)
    opt = OpticalSystem(su)
    tk = TimeKeeping()
    survey = SurveySimulation(su, opt, tk)
    survey.run_sim()
    make_trace_plot(survey)


if __name__ == '__main__':
    main()
