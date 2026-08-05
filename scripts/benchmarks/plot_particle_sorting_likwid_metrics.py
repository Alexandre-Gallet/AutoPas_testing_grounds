#!/usr/bin/env python3
"""Create thesis plots from LIKWID-based particle-sorting metrics.

Run the extraction script first:

  scripts/benchmarks/extract_particle_sorting_likwid_metrics.py --benchmark-root <benchmark-root>

This script reads:

  <benchmark-root>/derived_metrics/variant_metrics.csv

and writes PNG/PDF plots to:

  <benchmark-root>/plots/
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

BAR_COLOR = "#1F3A5F"
BASELINE_COLOR = "#9E2F2F"
GRID_COLOR = "#8A8A8A"
SERIES_COLORS = ["#1F3A5F", "#B95F21", "#2F7D6D", "#67507A"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        required=True,
        help="Scenario benchmark root, e.g. benchmarks/CoolMuc/homogeneous70-aos.",
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
            label="no-sorting baseline",
        )
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), frameon=False)

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
    series: list[tuple[str, list[float]]],
) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    width = 0.8 / max(len(series), 1)
    x_positions = list(range(len(variants)))
    offsets = [index * width - (len(series) - 1) * width / 2 for index in range(len(series))]

    for index, (offset, (label, values)) in enumerate(zip(offsets, series)):
        ax.bar(
            [x + offset for x in x_positions],
            values,
            width=width,
            label=label,
            color=SERIES_COLORS[index % len(SERIES_COLORS)],
        )

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(variants, rotation=35, ha="right")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=len(series), frameon=False)
    configure_axes(ax)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
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
    save_bar_plot(
        plt,
        plots_dir / "speedup_by_variant",
        "Speedup Relative to No Sorting",
        "Speedup [%]",
        [row["variant"] for row in ordered],
        [as_float(row, "speedup_percent_vs_no_sorting") for row in ordered],
        zero_line=True,
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


def save_l2_plots(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    variants = [row["variant"] for row in ordered]

    save_bar_plot(
        plt,
        plots_dir / "l2_miss_ratio_by_variant",
        "L2 Miss Ratio by Sorting Variant",
        "L2 misses / L2 requests",
        variants,
        [as_float(row, "likwid_l2_miss_ratio") for row in ordered],
        as_float(ordered[0], "likwid_l2_miss_ratio"),
    )
    save_bar_plot(
        plt,
        plots_dir / "l2_miss_rate_by_variant",
        "L2 Miss Rate by Sorting Variant",
        "LIKWID L2 miss rate",
        variants,
        [as_float(row, "likwid_l2_miss_rate") for row in ordered],
        as_float(ordered[0], "likwid_l2_miss_rate"),
    )


def save_cycle_stall_plot(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    variants = [row["variant"] for row in ordered]
    series = [
        ("L1D miss stall rate", [as_float(row, "likwid_l1d_miss_stall_rate_percent") for row in ordered]),
        ("L2 miss stall rate", [as_float(row, "likwid_l2_miss_stall_rate_percent") for row in ordered]),
        ("Memory-load stall rate", [as_float(row, "likwid_memory_load_stall_rate_percent") for row in ordered]),
    ]
    save_grouped_bar_plot(
        plt,
        plots_dir / "cycle_stall_rates_by_variant",
        "Memory-Related Stall Rates by Sorting Variant",
        "Stall rate [%]",
        variants,
        series,
    )


def save_l3_plots(plt, rows: list[dict[str, str]], plots_dir: Path) -> None:
    ordered = order_variant_rows(rows)
    variants = [row["variant"] for row in ordered]

    save_bar_plot(
        plt,
        plots_dir / "l3_data_volume_by_variant",
        "L3 Data Volume by Sorting Variant",
        "L3 data volume [GBytes]",
        variants,
        [as_float(row, "likwid_l3_data_volume_gbytes") for row in ordered],
        as_float(ordered[0], "likwid_l3_data_volume_gbytes"),
    )
    save_bar_plot(
        plt,
        plots_dir / "l3_bandwidth_by_variant",
        "L3 Bandwidth by Sorting Variant",
        "L3 bandwidth [MBytes/s]",
        variants,
        [as_float(row, "likwid_l3_bandwidth_mbytes_per_s") for row in ordered],
        as_float(ordered[0], "likwid_l3_bandwidth_mbytes_per_s"),
    )


def main() -> None:
    args = parse_args()
    root = args.benchmark_root
    derived_dir = root / "derived_metrics"
    plots_dir = args.output_dir or root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(derived_dir / "variant_metrics.csv")
    plt = require_matplotlib(root / ".matplotlib_cache")

    save_runtime_plot(plt, rows, plots_dir)
    save_speedup_plot(plt, rows, plots_dir)
    save_phase_runtime_stacked_plot(plt, rows, plots_dir)
    save_l2_plots(plt, rows, plots_dir)
    save_cycle_stall_plot(plt, rows, plots_dir)
    save_l3_plots(plt, rows, plots_dir)

    print(f"Wrote plots to {plots_dir}")


if __name__ == "__main__":
    main()
