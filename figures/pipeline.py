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
FILL_TOOL = "#F6F5F2"
EDGE_TOOL = "#8A8A85"
FILL_CORPUS = "#EBE4D6"
EDGE_CORPUS = "#8C7A55"

FIG_W, FIG_H = 7.0, 3.3
X, Y = 14.0, 6.6  # data-space extent (2 data units per inch)

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, X)
ax.set_ylim(0, Y)
ax.axis("off")
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

_checks = []  # (text artist, (x, y, w, h) of the box it must stay inside, label)


def box(x, y, w, h, fill, edge, lw=1.1, ls="solid"):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.13",
        facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls, zorder=2,
    ))
    return (x, y, w, h)


def arrow(x1, y1, x2, y2, style="-|>", lw=1.15, ls="solid"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=10, linewidth=lw,
        color=LINE, linestyle=ls, zorder=3,
        connectionstyle="arc3,rad=0", shrinkA=0, shrinkB=0,
    ))


def text(x, y, s, size=6.6, weight="normal", style="normal", color=INK,
         ha="center", inside=None):
    t = ax.text(x, y, s, fontsize=size, fontweight=weight, fontstyle=style,
                color=color, ha=ha, va="center", zorder=4, linespacing=1.5)
    if inside is not None:
        _checks.append((t, inside, s.replace("\n", " / ")))
    return t


# ── Main row ─────────────────────────────────────────────────────────
ROW_Y, ROW_H = 4.80, 1.28
b_in = box(0.15, ROW_Y, 1.95, ROW_H, FILL_IO, LINE)
b_s1 = box(2.75, ROW_Y, 3.75, ROW_H, FILL_STAGE1, EDGE_STAGE, lw=1.3)
b_s2 = box(7.15, ROW_Y, 3.75, ROW_H, FILL_STAGE2, EDGE_STAGE, lw=1.3)
b_out = box(11.55, ROW_Y, 2.30, ROW_H, FILL_IO, LINE)


def center(b):
    return b[0] + b[2] / 2


text(center(b_in), ROW_Y + 0.80, "Paper", size=9.0, weight="bold", inside=b_in)
text(center(b_in), ROW_Y + 0.42, "PDF / MD / text", size=6.5, color=GLOSS, inside=b_in)

text(center(b_s1), ROW_Y + 0.84, "Stage 1   Harsh Critic", size=9.0, weight="bold", inside=b_s1)
text(center(b_s1), ROW_Y + 0.44, "critical review of the paper", size=6.8, color="#33455C", inside=b_s1)

text(center(b_s2), ROW_Y + 0.84, "Stage 2   Merger", size=9.0, weight="bold", inside=b_s2)
text(center(b_s2), ROW_Y + 0.44, "verify, then calibrate by comparison", size=6.8, color="#26384C", inside=b_s2)

text(center(b_out), ROW_Y + 0.80, "Final review", size=9.0, weight="bold", inside=b_out)
text(center(b_out), ROW_Y + 0.42, "<score>  <decision>", size=6.5, color=GLOSS, inside=b_out)

MID_Y = ROW_Y + ROW_H / 2
arrow(b_in[0] + b_in[2], MID_Y, b_s1[0], MID_Y)
arrow(b_s1[0] + b_s1[2], MID_Y, b_s2[0], MID_Y)
arrow(b_s2[0] + b_s2[2], MID_Y, b_out[0], MID_Y)

text(X / 2, 6.32,
     "both stages run on the OpenAI Agents SDK or the Claude Agent SDK — same prompts, same tools",
     size=7.0, style="italic", color=GLOSS)

# ── Tool panels under each stage ─────────────────────────────────────
P_Y, P_H = 2.50, 1.85
p1 = box(2.55, P_Y, 4.05, P_H, FILL_TOOL, EDGE_TOOL, lw=0.9, ls=(0, (3, 2)))
p2 = box(6.95, P_Y, 4.35, P_H, FILL_TOOL, EDGE_TOOL, lw=0.9, ls=(0, (3, 2)))

text(center(p1), P_Y + 1.52, "read_file   ·   grep_file", size=7.6, weight="bold", inside=p1)
text(center(p1), P_Y + 0.72,
     "the paper never enters the\nprompt inline: read it in chunks,\nreason after each chunk before\nreading the next one",
     size=6.5, color=GLOSS, inside=p1)

text(center(p2), P_Y + 1.55, "read_file   ·   draft_review", size=7.6, weight="bold", inside=p2)
text(center(p2), P_Y + 1.24, "calibration_search", size=7.6, weight="bold", inside=p2)
text(center(p2), P_Y + 0.80, "1   cross-check each weakness vs. paper", size=6.5, color=GLOSS, inside=p2)
text(center(p2), P_Y + 0.52, "2   commit the draft before any anchor", size=6.5, color=GLOSS, inside=p2)
text(center(p2), P_Y + 0.24, "3   bracket the score band, then narrow", size=6.5, color=GLOSS, inside=p2)

arrow(center(p1), P_Y + P_H, center(p1), ROW_Y, style="<|-|>", lw=1.0)
arrow(center(p2), P_Y + P_H, center(p2), ROW_Y, style="<|-|>", lw=1.0)

# The paper stays on disk; both stages reach it only through the file tools.
arrow(center(b_in), ROW_Y, center(b_in), P_Y + P_H / 2, style="-", lw=0.9, ls=(0, (2, 2)))
arrow(center(b_in), P_Y + P_H / 2, p1[0], P_Y + P_H / 2, style="-|>", lw=0.9, ls=(0, (2, 2)))
text(center(b_in) + 0.10, P_Y + P_H / 2 + 0.26, "on disk", size=6.5, style="italic",
     color=GLOSS, ha="left")

# ── Calibration corpus ───────────────────────────────────────────────
C_Y, C_H = 0.22, 1.22
c = box(3.90, C_Y, 7.40, C_H, FILL_CORPUS, EDGE_CORPUS, lw=1.1)
text(center(c), C_Y + 0.76, "Calibration corpus   ·   13k human-reviewed papers",
     size=7.8, weight="bold", inside=c)
text(center(c), C_Y + 0.38, "vector retrieval, filtered to a band of real reviewer scores",
     size=6.5, color=GLOSS, inside=c)

arrow(center(p2), C_Y + C_H, center(p2), P_Y, style="<|-|>", lw=1.0)
text(center(p2) - 0.14, (C_Y + C_H + P_Y) / 2, "up to 3 batched\nRAG rounds", size=6.5,
     style="italic", color=GLOSS, ha="right")

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
