"""
Reference-run scatter for the README and the paper.

Pipeline score against the mean real reviewer score, one panel per model, for the
two reference runs shipped in results/. Renders figures/calibration_scatter.pdf
(vector) and figures/calibration_scatter.png (200 dpi) from the same source.

  python figures/calibration_scatter.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Validated categorical slots 1 and 2 (light surface), plus text/grid ink.
SURFACE = "#FCFCFB"
TEXT_1 = "#0B0B0B"
TEXT_2 = "#52514E"
GRID = "#E4E3DE"
ACCEPT = "#2A78D6"
REJECT = "#EB6834"
FIT = "#1F1F1E"
DIAG = "#9A9A94"

JITTER = 0.12  # ties are exact; spread them just enough to show density
RNG_SEED = 0

RUNS = [
    ("claude.csv", "Claude Sonnet 4.6"),
    ("deepseek.csv", "DeepSeek V4 Flash"),
]

root = Path(__file__).resolve().parent.parent
fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.55), sharex=True, sharey=True)
fig.patch.set_facecolor(SURFACE)

handles = {}
for ax, (fname, title) in zip(axes, RUNS):
    pred, gt, accepted = [], [], []
    with open(root / "results" / fname) as f:
        for row in csv.DictReader(f):
            pred.append(float(row["pred_score"]))
            gt.append(float(row["gt_avg_score"]))
            accepted.append(row["gt_binary"] == "Accept")
    pred = np.array(pred)
    gt = np.array(gt)
    accepted = np.array(accepted)

    rng = np.random.default_rng(RNG_SEED)
    px = pred + rng.uniform(-JITTER, JITTER, pred.size)
    py = gt + rng.uniform(-JITTER, JITTER, gt.size)

    slope, intercept = np.polyfit(pred, gt, 1)
    r = np.corrcoef(pred, gt)[0, 1]
    mae = np.abs(pred - gt).mean()

    ax.set_facecolor(SURFACE)
    ax.set_axisbelow(True)
    ax.grid(True, color=GRID, linewidth=0.6, linestyle="solid")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.8)

    lo, hi = -0.5, 8.8
    h_diag, = ax.plot([lo, hi], [lo, hi], color=DIAG, linewidth=1.0,
                      linestyle=(0, (4, 3)), zorder=2)
    xs = np.array([pred.min(), pred.max()])
    h_fit, = ax.plot(xs, slope * xs + intercept, color=FIT, linewidth=1.5, zorder=4)

    h_acc = ax.scatter(px[accepted], py[accepted], s=13, marker="o",
                       facecolor=ACCEPT, edgecolor=SURFACE, linewidth=0.45,
                       alpha=0.85, zorder=3)
    h_rej = ax.scatter(px[~accepted], py[~accepted], s=15, marker="v",
                       facecolor=REJECT, edgecolor=SURFACE, linewidth=0.45,
                       alpha=0.85, zorder=3)

    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")
    ax.set_xticks([0, 2, 4, 6, 8])
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.tick_params(colors=TEXT_2, labelsize=7.5, length=3, width=0.8)

    ax.set_title(title, fontsize=9.0, color=TEXT_1, fontweight="bold", pad=7)
    ax.set_xlabel("pipeline score", fontsize=8.0, color=TEXT_2)
    ax.text(0.035, 0.965,
            f"n = {pred.size}\nr = {r:.2f}\nMAE = {mae:.2f}",
            transform=ax.transAxes, fontsize=7.2, color=TEXT_2,
            ha="left", va="top", linespacing=1.5)

    handles.update({
        "accepted": h_acc, "rejected": h_rej,
        "y = x": h_diag, "least-squares fit": h_fit,
    })

axes[0].set_ylabel("mean real reviewer score", fontsize=8.0, color=TEXT_2)

fig.legend(handles.values(), handles.keys(), loc="lower center", ncol=4,
           frameon=False, fontsize=7.6, labelcolor=TEXT_2,
           handletextpad=0.5, columnspacing=1.9, bbox_to_anchor=(0.5, 0.028))
fig.text(0.5, 0.0, f"points jittered by up to {JITTER} on both axes to separate exact ties",
         ha="center", va="bottom", fontsize=6.6, color=TEXT_2, style="italic")

fig.subplots_adjust(left=0.085, right=0.985, top=0.93, bottom=0.20, wspace=0.10)

out = Path(__file__).resolve().parent
fig.savefig(out / "calibration_scatter.pdf", facecolor=SURFACE)
fig.savefig(out / "calibration_scatter.png", dpi=200, facecolor=SURFACE)
print(f"wrote {out/'calibration_scatter.pdf'} and {out/'calibration_scatter.png'}")
