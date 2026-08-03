#!/usr/bin/env python3
"""Create thesis plots from derived particle-sorting benchmark metrics.

Run the extraction script first:

    scripts/benchmarks/extract_particle_sorting_benchmark_metrics.py \
      --benchmark-root benchmarks/CoolMuc/homogeneous70

This script reads only the compact CSV files in derived_metrics/. It does not
parse raw VTune output.
"""

from __future__ import annotations

import argparse
import csv
import os
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

RUNTIME_PHASES = [
    "force_traversal",
    "verlet_construction",
    "soa_preparation",
    "sorting",
    "reference_rebuild_container_update",
    "time_integration",
    "other",
]

PHASE_LABELS = {
    "force_traversal": "Force traversal",
    "verlet_construction": "Verlet construction",
    "soa_preparation": "SoA preparation",
    "sorting": "Sorting",
    "reference_rebuild_container_update": "Reference rebuild/update",
    "time_integration": "Time integration",
    "other": "Other",
}

PHASE_COLORS = {
    "force_traversal": "#1F3A5F",
    "verlet_construction": "#2F7D6D",
    "soa_preparation": "#7A8F2A",
    "sorting": "#9E2F45",
    "reference_rebuild_container_update": "#67507A",
    "time_integration": "#B96F1D",
    "other": "#5E6670",
}

LOCALITY_PHASES = [
    "force_traversal",
    "verlet_construction",
]

LOCALITY_PHASE_LABELS = {
    "force_traversal": "Force traversal",
    "verlet_construction": "Verlet construction",
}

LOCALITY_PHASE_COLORS = {
    "force_traversal": "#1F3A5F",
    "verlet_construction": "#B95F21",
}

BAR_COLOR = "#1F3A5F"
BASELINE_COLOR = "#9E2F2F"
GRID_COLOR = "#8A8A8A"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        required=True,
        help="Scenario benchmark root, e.g. benchmarks/CoolMuc/homogeneous70.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output plot directory. Defaults to <benchmark-root>/plots.",
    )
    return parser.parse_args()


def require_matplotlib(config_dir: Path):
    os.environ.setdefault("MPLCONFIGDIR", str(config_dir))
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. Install it in the benchmark "
            "virtual environment or run only the extraction script."
        ) from exc
    return plt


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"Missing required derived table: {path}")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"Derived table has no data rows: {path}")
    return rows


def as_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value else 0.0


def order_variant_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_variant = {row["variant"]: row for row in rows}
    missing = [variant for variant in VARIANTS if variant not in by_variant]
    if missing:
        raise RuntimeError(f"Missing variants in derived table: {', '.join(missing)}")
    return [by_variant[variant] for variant in VARIANTS]


def configure_axes(ax) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID_COLOR, alpha=0.25, linewidth=0.8)
    ax.tick_params(axis="x", rotation=35)


def save_figure(fig, path_base: Path) -> None:
    fig.savefig(path_base.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")


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
    fig, ax = plt.subplots(figsize=(12, 5.8))
    ax.bar(variants, values, color=BAR_COLOR)

    if baseline_value is not None:
        ax.axhline(
            baseline_value,
            color=BASELINE_COLOR,
            linestyle="--",
            linewidth=1.3,
            label=baseline_label,
        )
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), frameon=False)

    if zero_line:
        ax.axhline(0.0, color="#555555", linewidth=0.8)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    configure_axes(ax)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save_figure(fig, path_base)
    plt.close(fig)


def save_grouped_bar_plot(
    plt,
    path_base: Path,
    title: str,
    ylabel: str,
    variants: list[str],
    series: dict[str, tuple[str, list[float]]],
) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    width = 0.8 / max(len(series), 1)
    x_positions = list(range(len(variants)))
    offsets = [index * width - (len(series) - 1) * width / 2 for index in range(len(series))]

    for offset, (phase, (label, values)) in zip(offsets, series.items()):
        ax.bar(
            [x + offset for x in x_positions],
            values,
            width=width,
            label=label,
            color=LOCALITY_PHASE_COLORS.get(phase, BAR_COLOR),
        )

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(variants, rotation=35, ha="right")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=len(series), frameon=False)
    configure_axes(ax)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save_figure(fig, path_base)
    plt.close(fig)


def save_runtime_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "mean_wall_clock_s")
    save_bar_plot(
        plt,
        plots_dir / "runtime_by_variant",
        "Runtime by Sorting Variant",
        "Mean wall-clock time [s]",
        [row["variant"] for row in ordered],
        [as_float(row, "mean_wall_clock_s") for row in ordered],
        baseline,
    )


def save_speedup_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    speedup_percent = [(as_float(row, "speedup_vs_no_sorting") - 1.0) * 100.0 for row in ordered]
    save_bar_plot(
        plt,
        plots_dir / "speedup_by_variant",
        "Speedup Relative to No Sorting",
        "Speedup [%]",
        [row["variant"] for row in ordered],
        speedup_percent,
        zero_line=True,
    )


def save_sorting_phase_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    save_bar_plot(
        plt,
        plots_dir / "sorting_phase_percent_by_variant",
        "Sorting Phase Share by Variant",
        "VTune Hotspots CPU time [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "phase_sorting_percent") for row in ordered],
        baseline_value=0.0,
        baseline_label="no-sorting baseline",
    )


def save_force_phase_time_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "phase_force_traversal_cpu_time_s_estimate")
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_phase_time_by_variant",
        "Force Traversal Time by Variant",
        "Estimated VTune Hotspots CPU time [s]",
        [row["variant"] for row in ordered],
        [as_float(row, "phase_force_traversal_cpu_time_s_estimate") for row in ordered],
        baseline,
    )


def save_whole_run_l3_miss_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "attributed_l3_misses_per_load")
    save_bar_plot(
        plt,
        plots_dir / "whole_run_l3_misses_per_load_by_variant",
        "Whole-Run L3 Misses per Load",
        "Attributed L3 misses / retired load",
        [row["variant"] for row in ordered],
        [as_float(row, "attributed_l3_misses_per_load") for row in ordered],
        baseline,
    )


def save_whole_run_l3_stall_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "attributed_l3_stalls_per_load")
    save_bar_plot(
        plt,
        plots_dir / "whole_run_l3_stalls_per_load_by_variant",
        "Whole-Run L3-Miss Stalls per Load",
        "Attributed L3-miss stalls / retired load",
        [row["variant"] for row in ordered],
        [as_float(row, "attributed_l3_stalls_per_load") for row in ordered],
        baseline,
    )


def save_force_l3_bound_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_force_traversal_l3_bound_percent")
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_l3_bound_by_variant",
        "Force Traversal L3 Bound by Variant",
        "L3 Bound [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_force_traversal_l3_bound_percent") for row in ordered],
        baseline,
    )


def save_force_dram_bound_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_force_traversal_dram_bound_percent")
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_dram_bound_by_variant",
        "Force Traversal DRAM Bound by Variant",
        "DRAM Bound [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_force_traversal_dram_bound_percent") for row in ordered],
        baseline,
    )


def save_force_average_latency_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    baseline = as_float(ordered[0], "memory_force_traversal_average_latency_cycles")
    save_bar_plot(
        plt,
        plots_dir / "force_traversal_average_latency_by_variant",
        "Force Traversal Memory Latency by Variant",
        "Average latency [cycles]",
        [row["variant"] for row in ordered],
        [as_float(row, "memory_force_traversal_average_latency_cycles") for row in ordered],
        baseline,
    )


def save_phase_runtime_stacked_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    variants = [row["variant"] for row in ordered]

    fig, ax = plt.subplots(figsize=(16, 9))
    bottom = [0.0] * len(ordered)

    for phase in RUNTIME_PHASES:
        values = [as_float(row, f"phase_{phase}_percent") for row in ordered]
        ax.bar(
            variants,
            values,
            bottom=bottom,
            label=PHASE_LABELS[phase],
            color=PHASE_COLORS[phase],
        )
        bottom = [old + value for old, value in zip(bottom, values)]

    ax.set_title("Runtime Decomposition by Phase")
    ax.set_ylabel("VTune Hotspots top-down CPU time [%]")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
    configure_axes(ax)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    save_figure(fig, plots_dir / "phase_runtime_stacked")
    plt.close(fig)


def save_l3_bound_by_phase_plot(plt, memory_phase_rows: list[dict[str, str]], plots_dir: Path) -> None:
    rows_by_variant_phase = {(row["variant"], row["phase"]): row for row in memory_phase_rows}
    series = {
        phase: (
            LOCALITY_PHASE_LABELS[phase],
            [as_float(rows_by_variant_phase[(variant, phase)], "l3_bound_percent") for variant in VARIANTS],
        )
        for phase in LOCALITY_PHASES
    }
    save_grouped_bar_plot(
        plt,
        plots_dir / "l3_bound_by_phase_and_variant",
        "L3 Bound in Main Particle-Access Phases",
        "L3 Bound [%]",
        VARIANTS,
        series,
    )


def save_dram_bound_by_phase_plot(plt, memory_phase_rows: list[dict[str, str]], plots_dir: Path) -> None:
    rows_by_variant_phase = {(row["variant"], row["phase"]): row for row in memory_phase_rows}
    series = {
        phase: (
            LOCALITY_PHASE_LABELS[phase],
            [as_float(rows_by_variant_phase[(variant, phase)], "dram_bound_percent") for variant in VARIANTS],
        )
        for phase in LOCALITY_PHASES
    }
    save_grouped_bar_plot(
        plt,
        plots_dir / "dram_bound_by_phase_and_variant",
        "DRAM Bound in Main Particle-Access Phases",
        "DRAM Bound [%]",
        VARIANTS,
        series,
    )


def save_average_latency_by_phase_plot(plt, memory_phase_rows: list[dict[str, str]], plots_dir: Path) -> None:
    rows_by_variant_phase = {(row["variant"], row["phase"]): row for row in memory_phase_rows}
    series = {
        phase: (
            LOCALITY_PHASE_LABELS[phase],
            [as_float(rows_by_variant_phase[(variant, phase)], "average_latency_cycles") for variant in VARIANTS],
        )
        for phase in LOCALITY_PHASES
    }
    save_grouped_bar_plot(
        plt,
        plots_dir / "average_latency_by_phase_and_variant",
        "Average Memory Latency in Main Particle-Access Phases",
        "Average latency [cycles]",
        VARIANTS,
        series,
    )


def main() -> None:
    args = parse_args()
    root = args.benchmark_root
    derived_dir = root / "derived_metrics"
    plots_dir = args.output_dir or root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    plt = require_matplotlib(root / ".matplotlib_cache")

    variant_rows = read_csv(derived_dir / "variant_metrics.csv")
    memory_phase_rows = read_csv(derived_dir / "memory_phase_metrics.csv")

    save_runtime_plot(plt, variant_rows, plots_dir)
    save_speedup_plot(plt, variant_rows, plots_dir)
    save_phase_runtime_stacked_plot(plt, variant_rows, plots_dir)
    save_sorting_phase_plot(plt, variant_rows, plots_dir)
    save_force_phase_time_plot(plt, variant_rows, plots_dir)
    save_whole_run_l3_miss_plot(plt, variant_rows, plots_dir)
    save_whole_run_l3_stall_plot(plt, variant_rows, plots_dir)
    save_force_l3_bound_plot(plt, variant_rows, plots_dir)
    save_force_dram_bound_plot(plt, variant_rows, plots_dir)
    save_force_average_latency_plot(plt, variant_rows, plots_dir)
    save_l3_bound_by_phase_plot(plt, memory_phase_rows, plots_dir)
    save_dram_bound_by_phase_plot(plt, memory_phase_rows, plots_dir)
    save_average_latency_by_phase_plot(plt, memory_phase_rows, plots_dir)

    print(f"Wrote plots to {plots_dir}")


if __name__ == "__main__":
    main()
