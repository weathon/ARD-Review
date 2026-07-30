"""
Pipeline figure for the paper and the README.

Renders figures/pipeline.pdf (vector, for LaTeX) and figures/pipeline.png
(200 dpi, for the README) from the same source. Every label is measured against
the box it belongs to after layout, so a text change that no longer fits prints
a warning instead of silently spilling over a border.

  python figures/pipeline.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from pathlib import Path

# Low-saturation palette. Identity comes from labels and border style; fills only
# carry hierarchy, so the figure stays readable printed in grayscale.
INK = "#1A1A1A"
LINE = "#3D3D3D"
GLOSS = "#3A3A3A"
FILL_IO = "#FFFFFF"
FILL_STAGE1 = "#E4EBF3"
FILL_STAGE2 = "#C5D4E2"
EDGE_STAGE = "#2E4A66"
FILL_SUB = "#EDF2F7"
FILL_GROUP = "#F7F6F3"
EDGE_GROUP = "#8A8A85"
FILL_CORPUS = "#EBE4D6"
EDGE_CORPUS = "#8C7A55"

FIG_W, FIG_H = 7.0, 3.7
X, Y = 14.0, 7.4  # data-space extent (2 data units per inch)

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, X)
ax.set_ylim(0, Y)
ax.axis("off")
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

_checks = []  # (text artist, (x, y, w, h) of the box it must stay inside, label)


def box(x, y, w, h, fill, edge, lw=1.1, ls="solid", z=2):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.13",
        facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls, zorder=z,
    ))
    return (x, y, w, h)


def arrow(x1, y1, x2, y2, style="-|>", lw=1.15, ls="solid"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=10, linewidth=lw,
        color=LINE, linestyle=ls, zorder=3,
        connectionstyle="arc3,rad=0", shrinkA=0, shrinkB=0,
    ))


def text(x, y, s, size=6.5, weight="normal", style="normal", color=INK,
         ha="center", inside=None):
    t = ax.text(x, y, s, fontsize=size, fontweight=weight, fontstyle=style,
                color=color, ha=ha, va="center", zorder=5, linespacing=1.5)
    if inside is not None:
        _checks.append((t, inside, s.replace("\n", " / ")))
    return t


def center(b):
    return b[0] + b[2] / 2


# ── Row 1: main flow ─────────────────────────────────────────────────
R_Y, R_H = 5.85, 1.15
b_in = box(0.15, R_Y, 1.95, R_H, FILL_IO, LINE)
b_s1 = box(2.75, R_Y, 3.75, R_H, FILL_STAGE1, EDGE_STAGE, lw=1.3)
b_s2 = box(7.15, R_Y, 3.75, R_H, FILL_STAGE2, EDGE_STAGE, lw=1.3)
b_out = box(11.55, R_Y, 2.30, R_H, FILL_IO, LINE)

text(center(b_in), R_Y + 0.72, "Paper", size=9.0, weight="bold", inside=b_in)
text(center(b_in), R_Y + 0.38, "PDF / MD / text", size=6.4, color=GLOSS, inside=b_in)

text(center(b_s1), R_Y + 0.74, "Stage 1   Harsh Critic", size=9.0, weight="bold", inside=b_s1)
text(center(b_s1), R_Y + 0.38, "critical review of the paper", size=6.7, color="#33455C", inside=b_s1)

text(center(b_s2), R_Y + 0.74, "Stage 2   Merger", size=9.0, weight="bold", inside=b_s2)
text(center(b_s2), R_Y + 0.38, "verify, anchor, calibrate", size=6.7, color="#26384C", inside=b_s2)

text(center(b_out), R_Y + 0.72, "Final review", size=9.0, weight="bold", inside=b_out)
text(center(b_out), R_Y + 0.38, "<score>  <decision>", size=6.4, color=GLOSS, inside=b_out)

MID = R_Y + R_H / 2
arrow(b_in[0] + b_in[2], MID, b_s1[0], MID)
arrow(b_s1[0] + b_s1[2], MID, b_s2[0], MID)
arrow(b_s2[0] + b_s2[2], MID, b_out[0], MID)

text(X / 2, 7.18,
     "both stages run on the OpenAI Agents SDK or the Claude Agent SDK — same prompts, same tools",
     size=7.0, style="italic", color=GLOSS)

# ── Row 2: the merger, expanded ──────────────────────────────────────
G_X, G_Y, G_W, G_H = 2.20, 2.60, 9.60, 2.55
grp = box(G_X, G_Y, G_W, G_H, FILL_GROUP, EDGE_GROUP, lw=1.0, ls=(0, (4, 2.5)))
text(center(grp), G_Y + G_H - 0.24, "Stage 2   Merger", size=8.0, weight="bold", inside=grp)

SUB_Y, SUB_H, SUB_W, GAP = 2.75, 2.02, 2.66, 0.55
s_a = box(2.45, SUB_Y, SUB_W, SUB_H, FILL_SUB, EDGE_STAGE, lw=1.0, z=3)
s_b = box(2.45 + SUB_W + GAP, SUB_Y, SUB_W, SUB_H, FILL_SUB, EDGE_STAGE, lw=1.0, z=3)
s_c = box(2.45 + 2 * (SUB_W + GAP), SUB_Y, SUB_W, SUB_H, FILL_SUB, EDGE_STAGE, lw=1.0, z=3)

text(center(s_a), SUB_Y + 1.66, "2a   Filter", size=8.2, weight="bold", inside=s_a)
text(center(s_a), SUB_Y + 0.78,
     "check every weakness\nagainst the paper, drop\nthe ones that do not\nhold, commit the draft",
     size=6.4, color=GLOSS, inside=s_a)

text(center(s_b), SUB_Y + 1.66, "2b   Anchor", size=8.2, weight="bold", inside=s_b)
text(center(s_b), SUB_Y + 0.78,
     "retrieve reviewed papers\nfrom every score band\nand bracket the band\nthis paper belongs to",
     size=6.4, color=GLOSS, inside=s_b)

text(center(s_c), SUB_Y + 1.66, "2c   Refine", size=8.2, weight="bold", inside=s_c)
text(center(s_c), SUB_Y + 0.78,
     "narrow inside that\nbracket, then set the\nscore and decision\nrelative to the anchors",
     size=6.4, color=GLOSS, inside=s_c)

arrow(s_a[0] + s_a[2], SUB_Y + SUB_H / 2, s_b[0], SUB_Y + SUB_H / 2)
arrow(s_b[0] + s_b[2], SUB_Y + SUB_H / 2, s_c[0], SUB_Y + SUB_H / 2)

# The group is the Merger box of row 1, opened up.
arrow(center(b_s2), R_Y, center(b_s2), G_Y + G_H, style="-", lw=1.0, ls=(0, (3, 2.5)))

# ── Calibration corpus ───────────────────────────────────────────────
C_X, C_Y, C_W, C_H = 4.30, 0.30, 7.20, 1.20
c = box(C_X, C_Y, C_W, C_H, FILL_CORPUS, EDGE_CORPUS, lw=1.1)
text(center(c), C_Y + 0.74, "Calibration corpus   ·   13k human-reviewed papers",
     size=7.8, weight="bold", inside=c)
text(center(c), C_Y + 0.38, "vector retrieval, filtered to a band of real reviewer scores",
     size=6.4, color=GLOSS, inside=c)

arrow(center(s_b), C_Y + C_H, center(s_b), G_Y, style="<|-|>", lw=1.0)
arrow(center(s_c), C_Y + C_H, center(s_c), G_Y, style="<|-|>", lw=1.0)
text((center(s_b) + center(s_c)) / 2, (C_Y + C_H + G_Y) / 2,
     "calibration_search\nup to 3 batched rounds", size=6.5, style="italic", color=GLOSS)

# ── Fit check ────────────────────────────────────────────────────────
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
inv = ax.transData.inverted()
overflow = 0
for t, (bx, by, bw, bh), label in _checks:
    e = t.get_window_extent(renderer)
    (x0, y0), (x1, y1) = inv.transform([(e.x0, e.y0), (e.x1, e.y1)])
    pad = 0.06
    if x0 < bx + pad or x1 > bx + bw - pad or y0 < by + pad or y1 > by + bh - pad:
        print(f"OVERFLOW: {label!r} extends to [{x0:.2f},{x1:.2f}]x[{y0:.2f},{y1:.2f}] "
              f"outside box [{bx:.2f},{bx+bw:.2f}]x[{by:.2f},{by+bh:.2f}]")
        overflow += 1
print(f"fit check: {len(_checks)} labels, {overflow} overflowing")

out_dir = Path(__file__).resolve().parent
fig.savefig(out_dir / "pipeline.pdf")
fig.savefig(out_dir / "pipeline.png", dpi=200)
print(f"wrote {out_dir/'pipeline.pdf'} and {out_dir/'pipeline.png'}")
