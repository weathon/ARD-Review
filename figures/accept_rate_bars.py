"""
Real accept/reject composition of each pipeline-score bin, for the README and the
paper.

One panel per reference run in results/. Bins are [k, k+1) on the pipeline score;
every column is normalised to 1, split into the share of papers that were really
accepted and really rejected. Renders figures/accept_rate_bars.pdf (vector) and
figures/accept_rate_bars.png (200 dpi) from the same source.

  python figures/accept_rate_bars.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Same entities, same colours as the scatter figure.
SURFACE = "#FCFCFB"
TEXT_1 = "#0B0B0B"
TEXT_2 = "#52514E"
GRID = "#E4E3DE"
ACCEPT = "#2A78D6"
REJECT = "#EB6834"

BIN_LO, BIN_HI = 1, 9  # [1,2) ... [8,9) covers both runs
GAP = 0.008  # surface gap between the two stacked segments
BAR_W = 0.62

RUNS = [
    ("claude.csv", "Claude Sonnet 4.6"),
    ("deepseek.csv", "DeepSeek V4 Flash"),
]

root = Path(__file__).resolve().parent.parent
fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.95), sharex=True, sharey=True)
fig.patch.set_facecolor(SURFACE)

edges = np.arange(BIN_LO, BIN_HI)
handles = {}
for ax, (fname, title) in zip(axes, RUNS):
    pred, accepted = [], []
    with open(root / "results" / fname) as f:
        for row in csv.DictReader(f):
            pred.append(float(row["pred_score"]))
            accepted.append(row["gt_binary"] == "Accept")
    pred = np.array(pred)
    accepted = np.array(accepted)

    ax.set_facecolor(SURFACE)
    ax.set_axisbelow(True)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6, linestyle="solid")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.8)

    for i, lo in enumerate(edges):
        mask = (pred >= lo) & (pred < lo + 1)
        if not mask.any():
            continue
        share = accepted[mask].mean()
        if share > 0:
            handles["accepted"] = ax.bar(i, share, width=BAR_W, color=ACCEPT, linewidth=0)
        if share < 1:
            bottom = share + GAP if share > 0 else 0.0
            handles["rejected"] = ax.bar(i, 1 - bottom, bottom=bottom, width=BAR_W,
                                         color=REJECT, linewidth=0)

    ax.set_xticks(range(len(edges)))
    ax.set_xticklabels([f"{lo}–{lo + 1}" for lo in edges])
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.tick_params(colors=TEXT_2, labelsize=7.2, length=3, width=0.8)

    ax.set_title(title, fontsize=9.0, color=TEXT_1, fontweight="bold", pad=7)
    ax.set_xlabel("pipeline score", fontsize=8.0, color=TEXT_2)

axes[0].set_ylabel("share of papers by real outcome", fontsize=8.0, color=TEXT_2)

order = ["accepted", "rejected"]
fig.legend([handles[k] for k in order], order, loc="lower center", ncol=2,
           frameon=False, fontsize=7.6, labelcolor=TEXT_2,
           handletextpad=0.6, columnspacing=2.2, bbox_to_anchor=(0.5, 0.01))

fig.subplots_adjust(left=0.095, right=0.985, top=0.90, bottom=0.22, wspace=0.08)

out = Path(__file__).resolve().parent
fig.savefig(out / "accept_rate_bars.pdf", facecolor=SURFACE)
fig.savefig(out / "accept_rate_bars.png", dpi=200, facecolor=SURFACE)
print(f"wrote {out/'accept_rate_bars.pdf'} and {out/'accept_rate_bars.png'}")
