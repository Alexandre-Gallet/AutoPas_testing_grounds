#!/usr/bin/env python3
"""Summarize raw md-flexible runtime measurements from CoolMuc.

This script is intentionally narrow: it only reads the `runtime/runtimes.csv`
files created by `scripts/slurm/runtime_one_variant.slurm` and writes one
summary CSV. VTune hotspots and VTune memory extraction should live in separate
scripts so each extraction step remains easy to inspect and validate.
"""

from __future__ import annotations

import argparse
import csv
import statistics
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        required=True,
        help="Scenario benchmark root, e.g. benchmarks/CoolMuc/homogeneous40.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to <benchmark-root>/derived_metrics/runtime_metrics.csv.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip variants without runtime/runtimes.csv instead of failing.",
    )
    return parser.parse_args()


def parse_variant_parts(variant: str) -> tuple[str, str]:
    """Split a benchmark variant name into sorting resolution and order."""
    if variant == "no-sorting":
        return "none", "none"

    resolution, order = variant.split("-", maxsplit=1)
    return resolution, order


def read_runtime_values(path: Path) -> list[float]:
    """Read wall-clock measurements from one runtime/runtimes.csv file."""
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"run_id", "wall_clock_s", "output_file"}

        if reader.fieldnames is None:
            raise RuntimeError(f"{path} is empty or has no CSV header")

        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RuntimeError(f"{path} is missing required columns: {missing}")

        values: list[float] = []
        for line_number, row in enumerate(reader, start=2):
            raw_value = row["wall_clock_s"]
            try:
                value = float(raw_value)
            except ValueError as error:
                raise RuntimeError(f"{path}:{line_number}: invalid wall_clock_s value {raw_value!r}") from error

            if value <= 0.0:
                raise RuntimeError(f"{path}:{line_number}: wall_clock_s must be positive, got {value}")

            values.append(value)

    if not values:
        raise RuntimeError(f"{path} contains no runtime measurements")

    return values


def summarize(values: list[float]) -> dict[str, float | int]:
    """Calculate the runtime summary statistics used in thesis plots."""
    return {
        "runs": len(values),
        "mean_wall_clock_s": statistics.fmean(values),
        "min_wall_clock_s": min(values),
        "max_wall_clock_s": max(values),
        "stddev_wall_clock_s": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def build_rows(benchmark_root: Path, allow_missing: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for variant in VARIANTS:
        runtimes_path = benchmark_root / variant / "runtime" / "runtimes.csv"

        if not runtimes_path.exists():
            if allow_missing:
                continue
            raise RuntimeError(f"Missing runtime measurements: {runtimes_path}")

        values = read_runtime_values(runtimes_path)
        summary = summarize(values)
        resolution, order = parse_variant_parts(variant)

        rows.append(
            {
                "scenario": benchmark_root.name,
                "variant": variant,
                "sorting_resolution": resolution,
                "sorting_order": order,
                "runs": str(summary["runs"]),
                "mean_wall_clock_s": f"{summary['mean_wall_clock_s']:.9f}",
                "min_wall_clock_s": f"{summary['min_wall_clock_s']:.9f}",
                "max_wall_clock_s": f"{summary['max_wall_clock_s']:.9f}",
                "stddev_wall_clock_s": f"{summary['stddev_wall_clock_s']:.9f}",
                "source_file": str(runtimes_path),
            }
        )

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("No runtime rows to write")

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    benchmark_root = args.benchmark_root
    output = args.output or benchmark_root / "derived_metrics" / "runtime_metrics.csv"

    rows = build_rows(benchmark_root, args.allow_missing)
    write_csv(output, rows)

    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
