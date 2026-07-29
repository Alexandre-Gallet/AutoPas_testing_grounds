#!/usr/bin/env python3
"""Create plots from derived particle-sorting 9-variant benchmark tables.

Run the extraction script first:

    python3 scripts/benchmarks/extract_particle_sorting_9variants_metrics.py

This script intentionally reads only files from the derived_metrics/ directory.
It does not parse raw VTune or Hyperfine output.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


VARIANTS = [
    "no-sorting",
    "cell-linear",
    "cell-morton",
    "cell-hilbert",
    "block-linear",
    "block-morton",
    "block-hilbert",
    "particle-linear",
    "particle-morton",
    "particle-hilbert",
]

PHASES = [
    "force_traversal",
    "verlet_construction",
    "sorting",
    "reference_rebuild_container_update",
    "time_integration",
    "other",
]

PHASE_LABELS = {
    "force_traversal": "Force traversal",
    "verlet_construction": "Verlet construction",
    "sorting": "Sorting",
    "reference_rebuild_container_update": "Reference rebuild/update",
    "time_integration": "Time integration",
    "other": "Other",
}

PHASE_COLORS = {
    "force_traversal": "#264653",
    "verlet_construction": "#2A9D8F",
    "sorting": "#B23A48",
    "reference_rebuild_container_update": "#6D597A",
    "time_integration": "#E9A03B",
    "other": "#6C757D",
}

BAR_COLOR = "#264653"

LOCALITY_PHASES = [
    "force_traversal",
    "verlet_construction",
]

LOCALITY_PHASE_LABELS = {
    "force_traversal": "Force traversal",
    "verlet_construction": "Verlet construction",
}

LOCALITY_PHASE_COLORS = {
    "force_traversal": "#264653",
    "verlet_construction": "#C46A2B",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=Path("benchmarks/particle-sorting-9variants"),
        help="Root directory containing the derived benchmark tables.",
    )
    return parser.parse_args()


def require_matplotlib():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. Install it in your benchmark "
            "environment or run only the extraction script."
        ) from exc
    return plt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value else 0.0


def order_variant_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_variant = {row["variant"]: row for row in rows}
    return [by_variant[variant] for variant in VARIANTS if variant in by_variant]


def save_bar_plot(
    plt,
    path_base: Path,
    title: str,
    ylabel: str,
    variants: list[str],
    values: list[float],
    baseline_value: float | None = None,
    baseline_label: str = "no-sorting baseline",
    zero_line: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(variants, values, color=BAR_COLOR)
    if baseline_value is not None:
        ax.axhline(
            baseline_value,
            color="#9E2F2F",
            linestyle="--",
            linewidth=1.2,
            label=baseline_label,
        )
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), frameon=False)
    if zero_line:
        ax.axhline(0.0, color="#555555", linewidth=0.8)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(path_base.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def save_grouped_bar_plot(
    plt,
    path_base: Path,
    title: str,
    ylabel: str,
    variants: list[str],
    series: dict[str, tuple[str, list[float]]],
) -> None:
    fig, ax = plt.subplots(figsize=(13, 5.5))
    width = 0.8 / max(len(series), 1)
    x_positions = list(range(len(variants)))
    offsets = [index * width - (len(series) - 1) * width / 2 for index in range(len(series))]

    for offset, (phase, (label, values)) in zip(offsets, series.items()):
        color = LOCALITY_PHASE_COLORS.get(phase, BAR_COLOR)
        ax.bar([x + offset for x in x_positions], values, width=width, label=label, color=color)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(variants, rotation=35, ha="right")
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=len(series), frameon=False)
    fig.tight_layout()
    fig.savefig(path_base.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def save_scatter_plot(
    plt,
    path_base: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    variants: list[str],
    x_values: list[float],
    y_values: list[float],
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(x_values, y_values, color="#3568a8")
    for variant, x_value, y_value in zip(variants, x_values, y_values):
        ax.annotate(variant, (x_value, y_value), textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.axhline(0.0, color="#555555", linewidth=0.8)
    ax.axvline(0.0, color="#555555", linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path_base.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def save_runtime_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "runtime_mean_s")
    # runtime_mean_s is the mean wall-clock runtime reported by Hyperfine.
    save_bar_plot(
        plt,
        plots_dir / "runtime_by_variant",
        "Runtime by Sorting Variant",
        "Mean Runtime [s]",
        [row["variant"] for row in ordered],
        [as_float(row, "runtime_mean_s") for row in ordered],
        baseline,
    )


def save_speedup_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    # speedup_percent = (runtime_baseline - runtime_variant) / runtime_baseline * 100.
    save_bar_plot(
        plt,
        plots_dir / "speedup_by_variant",
        "Speedup Relative to No Sorting",
        "Speedup [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "speedup_percent") for row in ordered],
        zero_line=True,
    )


def save_l3_miss_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "l3_miss_per_load")
    # l3_miss_per_load = MEM_LOAD_RETIRED.L3_MISS / MEM_INST_RETIRED.ALL_LOADS.
    save_bar_plot(
        plt,
        plots_dir / "l3_miss_per_load_by_variant",
        "Whole-Run L3 Misses per Load",
        "L3 Misses / Retired Load",
        [row["variant"] for row in ordered],
        [as_float(row, "l3_miss_per_load") for row in ordered],
        baseline,
    )


def save_l3_stalls_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "l3_stalls_per_load")
    # l3_stalls_per_load = MEMORY_ACTIVITY.STALLS_L3_MISS / MEM_INST_RETIRED.ALL_LOADS.
    save_bar_plot(
        plt,
        plots_dir / "l3_stalls_per_load_by_variant",
        "Whole-Run L3-Miss Stalls per Load",
        "L3-Miss Stalls / Retired Load",
        [row["variant"] for row in ordered],
        [as_float(row, "l3_stalls_per_load") for row in ordered],
        baseline,
    )


def save_force_l3_bound_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_topdown_force_traversal_l3_bound_percent")
    # Value comes from the VTune Memory top-down row for the force-traversal worker function.
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_l3_bound_by_variant",
        "Force Traversal L3 Bound by Sorting Variant",
        "L3 Bound [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_topdown_force_traversal_l3_bound_percent") for row in ordered],
        baseline,
    )


def save_force_dram_bound_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_topdown_force_traversal_dram_bound_percent")
    # Value comes from the VTune Memory top-down row for the force-traversal worker function.
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_dram_bound_by_variant",
        "Force Traversal DRAM Bound by Sorting Variant",
        "DRAM Bound [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_topdown_force_traversal_dram_bound_percent") for row in ordered],
        baseline,
    )


def save_force_average_latency_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_topdown_force_traversal_average_latency_cycles")
    # Value comes from the VTune Memory top-down row for the force-traversal worker function.
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_average_latency_by_variant",
        "Force Traversal Memory Latency by Sorting Variant",
        "Average Latency [cycles]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_topdown_force_traversal_average_latency_cycles") for row in ordered],
        baseline,
    )


def save_force_phase_time_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "phase_force_traversal_cpu_time_s_estimate")
    # phase_force_traversal_cpu_time_s_estimate =
    # phase_force_traversal_percent / 100 * total VTune Hotspots CPU time.
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_phase_time_by_variant",
        "Force Traversal Time by Sorting Variant",
        "Estimated VTune Hotspots CPU time [s]",
        [row["variant"] for row in ordered],
        [as_float(row, "phase_force_traversal_cpu_time_s_estimate") for row in ordered],
        baseline,
    )


def save_l3_bound_by_phase_and_variant_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    variants = [row["variant"] for row in ordered]
    series = {
        phase: (
            LOCALITY_PHASE_LABELS[phase],
            [as_float(row, f"memory_topdown_{phase}_l3_bound_percent") for row in ordered],
        )
        for phase in LOCALITY_PHASES
    }
    save_grouped_bar_plot(
        plt,
        plots_dir / "l3_bound_by_phase_and_variant",
        "L3 Bound in Main Particle-Access Phases",
        "L3 Bound [%]",
        variants,
        series,
    )


def save_phase_runtime_stacked_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)

    fig, ax = plt.subplots(figsize=(16, 9))
    bottom = [0.0] * len(VARIANTS)
    for phase in PHASES:
        values = [as_float(row, f"phase_{phase}_percent") for row in ordered]
        ax.bar(
            [row["variant"] for row in ordered],
            values,
            bottom=bottom,
            label=PHASE_LABELS[phase],
            color=PHASE_COLORS[phase],
        )
        bottom = [old + value for old, value in zip(bottom, values)]

    ax.set_title("Runtime Decomposition by Phase")
    ax.set_ylabel("VTune Hotspots top-down CPU time [%]")
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=35)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3, frameon=False)
    # Phase percentages are inclusive VTune top-down call-path totals.
    # Reference rebuild/update excludes nested sorting so the stacked values remain additive.
    fig.tight_layout(rect=(0, 0.24, 1, 1))
    fig.savefig((plots_dir / "phase_runtime_stacked").with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig((plots_dir / "phase_runtime_stacked").with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    plt = require_matplotlib()

    root = args.benchmark_root
    derived_dir = root / "derived_metrics"
    plots_dir = root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    variant_rows = read_csv(derived_dir / "variant_metrics.csv")

    save_runtime_plot(plt, variant_rows, plots_dir)
    save_speedup_plot(plt, variant_rows, plots_dir)
    save_l3_miss_plot(plt, variant_rows, plots_dir)
    save_l3_stalls_plot(plt, variant_rows, plots_dir)
    save_phase_runtime_stacked_plot(plt, variant_rows, plots_dir)
    save_force_phase_time_plot(plt, variant_rows, plots_dir)
    save_force_l3_bound_plot(plt, variant_rows, plots_dir)
    save_force_dram_bound_plot(plt, variant_rows, plots_dir)
    save_force_average_latency_plot(plt, variant_rows, plots_dir)
    save_l3_bound_by_phase_and_variant_plot(plt, variant_rows, plots_dir)

    print(f"Wrote plots to {plots_dir}")


if __name__ == "__main__":
    main()
