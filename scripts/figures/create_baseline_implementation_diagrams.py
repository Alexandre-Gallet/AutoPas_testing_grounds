#!/usr/bin/env python3
"""Generate baseline implementation diagrams for the thesis.

The script writes PDF figures into the LaTeX project's existing figures
directory. It uses matplotlib only, so the diagrams can be edited with the same
tooling as the benchmark plots.
"""

from __future__ import annotations

import os
from pathlib import Path

# Keep matplotlib from trying to write into ~/.config on systems where that is
# not writable from the execution environment.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/autopas-thesis-matplotlib")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle


REPO_ROOT = Path(__file__).resolve().parents[2]
FIGURE_DIR = REPO_ROOT / "writing" / "studentstarterclues-master-ThesisTemplate" / "ThesisTemplate" / "figures"

BLUE = "#244C8F"
LIGHT_BLUE = "#DCE8F8"
GREEN = "#2F6F4E"
LIGHT_GREEN = "#DCEFE5"
ORANGE = "#B7652A"
LIGHT_ORANGE = "#F4E2D3"
GRAY = "#52565A"
LIGHT_GRAY = "#ECEFF2"


def add_box(ax, xy, width, height, text, *, fc=LIGHT_BLUE, ec=BLUE, fontsize=10, rounded=True):
    """Add a labeled box in axes data coordinates."""
    x, y = xy
    if rounded:
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.08,rounding_size=0.08",
            linewidth=1.4,
            edgecolor=ec,
            facecolor=fc,
        )
    else:
        patch = Rectangle((x, y), width, height, linewidth=1.2, edgecolor=ec, facecolor=fc)
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=fontsize)
    return patch


def add_arrow(ax, start, end, *, color=GRAY, dashed=False, text=None, text_offset=(0, 0)):
    """Add an arrow and optional label."""
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(
            arrowstyle="->",
            lw=1.6,
            color=color,
            linestyle="--" if dashed else "-",
            shrinkA=3,
            shrinkB=3,
        ),
    )
    if text:
        ax.text(
            (start[0] + end[0]) / 2 + text_offset[0],
            (start[1] + end[1]) / 2 + text_offset[1],
            text,
            ha="center",
            va="center",
            fontsize=8,
            color=color,
        )


def finish(ax, filename: str):
    """Common final formatting and export."""
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / filename
    ax.figure.savefig(path, bbox_inches="tight")
    plt.close(ax.figure)
    print(path)


def storage_model():
    """Draw global ParticleVector ownership with reference cells pointing into it."""
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)

    add_box(ax, (3.2, 3.35), 3.6, 0.65, "global ParticleVector", fc=LIGHT_BLUE, ec=BLUE, fontsize=12)

    particle_x = [1.3, 2.55, 3.8, 5.05, 6.3, 7.55]
    labels = [r"$p_0$", r"$p_1$", r"$p_2$", r"$p_3$", r"$p_4$", r"$p_5$"]
    for x, label in zip(particle_x, labels):
        add_box(ax, (x, 2.35), 0.85, 0.55, label, fc="#EAF1FB", ec=BLUE, fontsize=11, rounded=False)
    ax.add_patch(Rectangle((1.15, 2.22), 7.45, 0.82, fill=False, edgecolor=BLUE, linewidth=1.5))
    add_arrow(ax, (5.0, 3.33), (5.0, 3.05), color=BLUE)

    cell_positions = [(1.25, 0.9), (4.05, 0.9), (6.85, 0.9)]
    for i, pos in enumerate(cell_positions):
        add_box(ax, pos, 1.9, 0.75, f"Reference\nParticleCell {i}", fc=LIGHT_GRAY, ec=GRAY, fontsize=9)

    pointer_pairs = [
        ((2.20, 1.66), (1.73, 2.35)),
        ((2.20, 1.66), (2.98, 2.35)),
        ((5.00, 1.66), (4.23, 2.35)),
        ((7.80, 1.66), (5.48, 2.35)),
        ((7.80, 1.66), (6.73, 2.35)),
        ((7.80, 1.66), (7.98, 2.35)),
    ]
    for start, end in pointer_pairs:
        add_arrow(ax, start, end, color=GRAY)

    ax.text(
        5.0,
        0.25,
        "Cells do not own particles; they store references into the global particle vector.",
        ha="center",
        va="center",
        fontsize=10,
        color=GRAY,
    )

    finish(ax, "baseline_storage_model.pdf")


def verlet_lifecycle():
    """Draw the simplified Verlet-list lifecycle and rebuild path."""
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4.2)

    boxes = {
        "integrate": ((0.35, 3.0), "time integration\nupdate positions", LIGHT_BLUE, BLUE),
        "check": ((3.1, 3.0), "check container\nand list validity", LIGHT_BLUE, BLUE),
        "update": ((5.85, 3.0), "container update\nmigrate particles", LIGHT_ORANGE, ORANGE),
        "refs": ((8.6, 3.0), "rebuild dirty\ncell references", LIGHT_ORANGE, ORANGE),
        "lists": ((8.6, 1.35), "build AoS\nVerlet lists", LIGHT_ORANGE, ORANGE),
        "soa": ((5.85, 1.35), "if SoA:\nbuild index lists", LIGHT_ORANGE, ORANGE),
        "force": ((3.1, 1.35), "force traversal\nover Verlet lists", LIGHT_BLUE, BLUE),
        "next": ((0.35, 1.35), "next iteration", LIGHT_BLUE, BLUE),
    }
    centers = {}
    for name, (pos, label, fc, ec) in boxes.items():
        add_box(ax, pos, 2.1, 0.7, label, fc=fc, ec=ec, fontsize=9)
        centers[name] = (pos[0] + 1.05, pos[1] + 0.35)

    add_arrow(ax, (2.45, 3.35), (3.10, 3.35), color=BLUE)
    add_arrow(ax, (5.20, 3.35), (5.85, 3.35), color=ORANGE, text="rebuild", text_offset=(0, 0.28))
    add_arrow(ax, (7.95, 3.35), (8.60, 3.35), color=ORANGE)
    add_arrow(ax, (9.65, 3.0), (9.65, 2.05), color=ORANGE)
    add_arrow(ax, (8.60, 1.70), (7.95, 1.70), color=ORANGE)
    add_arrow(ax, (5.85, 1.70), (5.20, 1.70), color=BLUE)
    add_arrow(ax, (3.10, 1.70), (2.45, 1.70), color=BLUE)
    add_arrow(ax, (1.40, 1.35), (1.40, 3.0), color=BLUE)
    add_arrow(ax, (4.15, 3.0), (4.15, 2.05), color=GRAY, dashed=True, text="still valid", text_offset=(0.65, 0))

    ax.text(
        6.0,
        0.45,
        "Sorting is naturally placed in the rebuild/update path, before neighbor-list construction.",
        ha="center",
        va="center",
        fontsize=10,
        color=GRAY,
    )

    finish(ax, "baseline_verlet_lifecycle.pdf")


def aos_soa_traversal():
    """Draw why AoS and SoA expose sorted order differently."""
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4.4)

    add_box(ax, (0.65, 3.35), 3.5, 0.6, "AoS traversal", fc=LIGHT_GRAY, ec=GRAY, fontsize=12)
    add_box(ax, (0.95, 2.35), 2.9, 0.65, "unordered_map\ncenter pointer -> neighbors", fc="#F3F3F3", ec=GRAY, fontsize=9)
    aos_order = [r"$p_7$", r"$p_2$", r"$p_9$", r"$p_1$"]
    for i, label in enumerate(aos_order):
        add_box(ax, (0.75 + i * 0.85, 1.35), 0.62, 0.5, label, fc="#EAF1FB", ec=GRAY, fontsize=10, rounded=False)
    add_arrow(ax, (2.40, 3.35), (2.40, 3.02), color=GRAY)
    add_arrow(ax, (2.40, 2.35), (2.40, 1.87), color=GRAY)
    ax.text(
        2.4,
        0.55,
        "bucket / pointer order is not guaranteed\nto match global storage order",
        ha="center",
        va="center",
        fontsize=9,
        color=GRAY,
    )

    add_box(ax, (6.85, 3.35), 3.5, 0.6, "SoA traversal", fc=LIGHT_GREEN, ec=GREEN, fontsize=12)
    add_box(ax, (7.15, 2.35), 2.9, 0.65, "index order\n0, 1, 2, ...", fc="#EEF7F1", ec=GREEN, fontsize=9)
    soa_order = [r"$p_0$", r"$p_1$", r"$p_2$", r"$p_3$"]
    for i, label in enumerate(soa_order):
        add_box(ax, (7.0 + i * 0.85, 1.35), 0.62, 0.5, label, fc="#EAF1FB", ec=GREEN, fontsize=10, rounded=False)
    add_arrow(ax, (8.60, 3.35), (8.60, 3.02), color=GREEN)
    add_arrow(ax, (8.60, 2.35), (8.60, 1.87), color=GREEN)
    ax.text(
        8.6,
        0.55,
        "if the SoA buffer is loaded from sorted storage,\nindex iteration follows sorted particle order",
        ha="center",
        va="center",
        fontsize=9,
        color=GRAY,
    )

    finish(ax, "baseline_aos_soa_traversal.pdf")


def main() -> None:
    storage_model()
    verlet_lifecycle()
    aos_soa_traversal()


if __name__ == "__main__":
    main()
