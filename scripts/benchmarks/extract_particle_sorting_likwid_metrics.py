#!/usr/bin/env python3
"""Extract runtime, VTune Hotspots, and LIKWID metrics for one scenario.

Expected input layout:

  <benchmark-root>/<variant>/runtime/runtimes.csv
  <benchmark-root>/<variant>/vtune_hotspots/top_down.csv
  <benchmark-root>/<variant>/likwid/likwid-L2CACHE-summary.txt
  <benchmark-root>/<variant>/likwid/likwid-CYCLE_STALLS-summary.txt
  <benchmark-root>/<variant>/likwid/likwid-L3-summary.txt

The script writes:

  <benchmark-root>/derived_metrics/variant_metrics.csv

The table intentionally contains only the metrics used by the current thesis
plots: runtime, VTune top-down runtime phases, LIKWID L2 cache metrics,
LIKWID cycle-stall rates, and LIKWID L3 traffic.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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


@dataclass(frozen=True)
class MatchRule:
    """String rule for selecting one semantically meaningful VTune row."""

    phase: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    required: bool = True


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
        help="Output directory. Defaults to <benchmark-root>/derived_metrics.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip missing variant directories. Existing but malformed files still fail.",
    )
    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing required file: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Required file is empty: {path}")


def read_csv(path: Path) -> list[dict[str, str]]:
    require_file(path)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames is None:
            raise RuntimeError(f"{path} is empty or has no CSV header")
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"{path} has no data rows")
    return rows


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def require_float(value: str | None, context: str) -> float:
    parsed = parse_float(value)
    if parsed is None:
        raise RuntimeError(f"Missing numeric value while reading {context}: {value!r}")
    return parsed


def format_float(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.9f}"


def parse_variant_parts(variant: str) -> tuple[str, str]:
    if variant == "no-sorting":
        return "none", "none"
    resolution, order = variant.split("-", maxsplit=1)
    return resolution, order


def parse_yaml_metadata(input_yaml: Path) -> dict[str, str]:
    require_file(input_yaml)
    text = input_yaml.read_text()

    particle_count = ""
    particle_match = re.search(r"particles-per-dimension\s*:\s*\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]", text)
    if particle_match:
        x, y, z = (int(value) for value in particle_match.groups())
        particle_count = str(x * y * z)

    data_layout = ""
    data_layout_match = re.search(r"data-layout\s*:\s*\[([^\]]+)\]", text)
    if data_layout_match:
        data_layout = data_layout_match.group(1).strip()

    iterations = ""
    iterations_match = re.search(r"iterations\s*:\s*(\d+)", text)
    if iterations_match:
        iterations = iterations_match.group(1)

    neighbor_sorting = ""
    neighbor_sorting_match = re.search(r"verlet-neighbor-list-sorting-enabled\s*:\s*(true|false)", text)
    if neighbor_sorting_match:
        neighbor_sorting = neighbor_sorting_match.group(1)

    return {
        "particle_count": particle_count,
        "data_layout": data_layout,
        "iterations": iterations,
        "neighbor_list_sorting_enabled": neighbor_sorting,
    }


def read_runtime_summary(runtimes_path: Path) -> dict[str, float | int]:
    rows = read_csv(runtimes_path)
    required_columns = {"run_id", "wall_clock_s", "output_file"}
    missing_columns = required_columns.difference(rows[0].keys())
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise RuntimeError(f"{runtimes_path} is missing required columns: {missing}")

    values: list[float] = []
    for index, row in enumerate(rows, start=2):
        value = parse_float(row.get("wall_clock_s"))
        if value is None or value <= 0.0:
            raise RuntimeError(f"{runtimes_path}:{index}: invalid wall_clock_s value {row.get('wall_clock_s')!r}")
        values.append(value)

    if not values:
        raise RuntimeError(f"{runtimes_path} contains no runtime measurements")

    return {
        "runs": len(values),
        "mean_wall_clock_s": statistics.fmean(values),
        "min_wall_clock_s": min(values),
        "max_wall_clock_s": max(values),
        "stddev_wall_clock_s": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def row_text(row: dict[str, str] | None) -> str:
    if row is None:
        return ""
    return " ".join(
        value
        for value in (
            row.get("Function Stack", ""),
            row.get("Function", ""),
            row.get("Function (Full)", ""),
            row.get("Source File", ""),
        )
        if value
    )


def contains_all(text: str, needles: Iterable[str]) -> bool:
    return all(needle in text for needle in needles)


def contains_none(text: str, needles: Iterable[str]) -> bool:
    return all(needle not in text for needle in needles)


def find_first_row(rows: list[dict[str, str]], rule: MatchRule) -> dict[str, str] | None:
    for row in rows:
        text = row_text(row)
        if contains_all(text, rule.include) and contains_none(text, rule.exclude):
            return row
    if rule.required:
        includes = ", ".join(rule.include)
        excludes = ", ".join(rule.exclude) if rule.exclude else "-"
        raise RuntimeError(f"Could not find VTune row for phase={rule.phase}, include=[{includes}], exclude=[{excludes}]")
    return None


def top_down_total(row: dict[str, str] | None, top_down_path: Path, phase: str) -> float:
    if row is None:
        return 0.0
    return require_float(row.get("CPU Time:Total"), f"{top_down_path}, phase={phase}, column=CPU Time:Total")


def extract_runtime_phase_percentages(top_down_path: Path) -> tuple[dict[str, float], dict[str, str]]:
    rows = read_csv(top_down_path)

    force_row = find_first_row(
        rows,
        MatchRule(
            phase="force_traversal",
            include=("VLListIterationTraversal", "traverseParticles"),
            exclude=("_omp_fn",),
        ),
    )
    verlet_row = find_first_row(
        rows,
        MatchRule(
            phase="verlet_construction",
            include=("LCC08Traversal", "traverseParticles"),
            exclude=("_omp_fn",),
        ),
    )
    update_container_row = find_first_row(
        rows,
        MatchRule(
            phase="reference_rebuild_container_update",
            include=("AutoPas", "updateContainer"),
            required=False,
        ),
    )
    sorting_row = find_first_row(
        rows,
        MatchRule(
            phase="sorting",
            include=("sortParticlesByConfiguredKey",),
            required=False,
        ),
    )
    soa_preparation_row = find_first_row(
        rows,
        MatchRule(
            phase="soa_preparation",
            include=("generateSoAListFromAoSVerletLists",),
            required=False,
        ),
    )
    position_row = find_first_row(
        rows,
        MatchRule(
            phase="time_integration_position",
            include=("TimeDiscretization::calculatePositionsAndResetForces",),
            exclude=("_omp_fn",),
            required=False,
        ),
    )
    velocity_row = find_first_row(
        rows,
        MatchRule(
            phase="time_integration_velocity",
            include=("TimeDiscretization::calculateVelocities",),
            exclude=("_omp_fn",),
            required=False,
        ),
    )

    force = top_down_total(force_row, top_down_path, "force_traversal")
    verlet = top_down_total(verlet_row, top_down_path, "verlet_construction")
    update_total = top_down_total(update_container_row, top_down_path, "reference_rebuild_container_update")
    sorting = top_down_total(sorting_row, top_down_path, "sorting")
    soa_preparation = top_down_total(soa_preparation_row, top_down_path, "soa_preparation")
    position = top_down_total(position_row, top_down_path, "time_integration_position")
    velocity = top_down_total(velocity_row, top_down_path, "time_integration_velocity")

    reference_rebuild = max(update_total - sorting, 0.0)
    time_integration = position + velocity
    known_sum = force + verlet + soa_preparation + sorting + reference_rebuild + time_integration
    other = max(100.0 - known_sum, 0.0)

    percentages = {
        "force_traversal": force,
        "verlet_construction": verlet,
        "soa_preparation": soa_preparation,
        "sorting": sorting,
        "reference_rebuild_container_update": reference_rebuild,
        "time_integration": time_integration,
        "other": other,
    }
    matches = {
        "force_traversal": row_text(force_row),
        "verlet_construction": row_text(verlet_row),
        "soa_preparation": row_text(soa_preparation_row),
        "sorting": row_text(sorting_row),
        "reference_rebuild_container_update": row_text(update_container_row),
        "time_integration": f"{row_text(position_row)} | {row_text(velocity_row)}",
        "other": "100 - selected runtime phases",
    }
    return percentages, matches


def extract_likwid_metric(summary_path: Path, metric_name: str) -> float:
    require_file(summary_path)
    pattern = re.compile(rf"^\|\s*{re.escape(metric_name)}\s*\|\s*([-+0-9.eE]+)\s*\|")
    for line in summary_path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            return float(match.group(1))
    raise RuntimeError(f"Could not find LIKWID metric {metric_name!r} in {summary_path}")


def extract_likwid_metrics(variant_dir: Path) -> dict[str, float]:
    likwid_dir = variant_dir / "likwid"
    l2cache = likwid_dir / "likwid-L2CACHE-summary.txt"
    cycle_stalls = likwid_dir / "likwid-CYCLE_STALLS-summary.txt"
    l3 = likwid_dir / "likwid-L3-summary.txt"

    return {
        "likwid_l2_request_rate": extract_likwid_metric(l2cache, "L2 request rate"),
        "likwid_l2_miss_rate": extract_likwid_metric(l2cache, "L2 miss rate"),
        "likwid_l2_miss_ratio": extract_likwid_metric(l2cache, "L2 miss ratio"),
        "likwid_execution_stall_rate_percent": extract_likwid_metric(cycle_stalls, "Execution stall rate [%]"),
        "likwid_l1d_miss_stall_rate_percent": extract_likwid_metric(cycle_stalls, "Stalls caused by L1D misses rate [%]"),
        "likwid_l2_miss_stall_rate_percent": extract_likwid_metric(cycle_stalls, "Stalls caused by L2 misses rate [%]"),
        "likwid_memory_load_stall_rate_percent": extract_likwid_metric(cycle_stalls, "Stalls caused by memory loads rate [%]"),
        "likwid_l3_bandwidth_mbytes_per_s": extract_likwid_metric(l3, "L3 bandwidth [MBytes/s]"),
        "likwid_l3_data_volume_gbytes": extract_likwid_metric(l3, "L3 data volume [GBytes]"),
    }


def build_rows(benchmark_root: Path, allow_missing: bool) -> list[dict[str, str]]:
    contexts: dict[str, dict[str, object]] = {}

    for variant in VARIANTS:
        variant_dir = benchmark_root / variant
        if not variant_dir.exists():
            if allow_missing:
                continue
            raise RuntimeError(f"Missing variant directory: {variant_dir}")

        input_yaml = benchmark_root / "inputs" / f"{variant}.yaml"
        runtimes_path = variant_dir / "runtime" / "runtimes.csv"
        hotspots_top_down_path = variant_dir / "vtune_hotspots" / "top_down.csv"

        for path in (input_yaml, runtimes_path, hotspots_top_down_path):
            require_file(path)

        runtime_summary = read_runtime_summary(runtimes_path)
        phase_percentages, phase_matches = extract_runtime_phase_percentages(hotspots_top_down_path)
        likwid_metrics = extract_likwid_metrics(variant_dir)
        yaml_metadata = parse_yaml_metadata(input_yaml)

        contexts[variant] = {
            "runtime_summary": runtime_summary,
            "phase_percentages": phase_percentages,
            "phase_matches": phase_matches,
            "likwid_metrics": likwid_metrics,
            "yaml_metadata": yaml_metadata,
        }

    if not contexts:
        raise RuntimeError(f"No variants found under {benchmark_root}")
    if "no-sorting" not in contexts:
        raise RuntimeError("The no-sorting baseline is required to calculate speedups")

    baseline_runtime = contexts["no-sorting"]["runtime_summary"]["mean_wall_clock_s"]  # type: ignore[index]
    assert isinstance(baseline_runtime, float)

    rows: list[dict[str, str]] = []
    for variant in VARIANTS:
        if variant not in contexts:
            continue

        context = contexts[variant]
        runtime_summary = context["runtime_summary"]  # type: ignore[assignment]
        phase_percentages = context["phase_percentages"]  # type: ignore[assignment]
        phase_matches = context["phase_matches"]  # type: ignore[assignment]
        likwid_metrics = context["likwid_metrics"]  # type: ignore[assignment]
        yaml_metadata = context["yaml_metadata"]  # type: ignore[assignment]

        assert isinstance(runtime_summary, dict)
        assert isinstance(phase_percentages, dict)
        assert isinstance(phase_matches, dict)
        assert isinstance(likwid_metrics, dict)
        assert isinstance(yaml_metadata, dict)

        mean_runtime = runtime_summary["mean_wall_clock_s"]
        assert isinstance(mean_runtime, float)
        resolution, order = parse_variant_parts(variant)

        row: dict[str, str] = {
            "variant": variant,
            "resolution": resolution,
            "order": order,
            "particle_count": str(yaml_metadata["particle_count"]),
            "data_layout": str(yaml_metadata["data_layout"]),
            "iterations": str(yaml_metadata["iterations"]),
            "neighbor_list_sorting_enabled": str(yaml_metadata["neighbor_list_sorting_enabled"]),
            "runs": str(runtime_summary["runs"]),
            "mean_wall_clock_s": format_float(mean_runtime),
            "min_wall_clock_s": format_float(runtime_summary["min_wall_clock_s"]),  # type: ignore[arg-type]
            "max_wall_clock_s": format_float(runtime_summary["max_wall_clock_s"]),  # type: ignore[arg-type]
            "stddev_wall_clock_s": format_float(runtime_summary["stddev_wall_clock_s"]),  # type: ignore[arg-type]
            "speedup_vs_no_sorting": format_float(baseline_runtime / mean_runtime),
            "speedup_percent_vs_no_sorting": format_float((baseline_runtime / mean_runtime - 1.0) * 100.0),
        }

        for phase in RUNTIME_PHASES:
            percent = phase_percentages[phase]
            row[f"phase_{phase}_percent"] = format_float(percent)
            row[f"phase_{phase}_wall_time_s_estimate"] = format_float(mean_runtime * percent / 100.0)
            row[f"phase_{phase}_matched_row"] = str(phase_matches[phase])

        for metric_name, value in likwid_metrics.items():
            row[metric_name] = format_float(value)

        rows.append(row)

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows to write to {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    benchmark_root = args.benchmark_root
    output_dir = args.output_dir or benchmark_root / "derived_metrics"
    rows = build_rows(benchmark_root, args.allow_missing)
    output_path = output_dir / "variant_metrics.csv"
    write_csv(output_path, rows)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
