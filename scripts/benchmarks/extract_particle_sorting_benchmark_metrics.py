#!/usr/bin/env python3
"""Extract derived metrics from one particle-sorting benchmark scenario.

The script expects the directory layout produced by the CoolMuc SLURM
benchmark scripts:

  <benchmark-root>/inputs/<variant>.yaml
  <benchmark-root>/<variant>/runtime/runtimes.csv
  <benchmark-root>/<variant>/vtune_hotspots/{summary,top_down}.csv
  <benchmark-root>/<variant>/vtune_memory/{top_down,hw_events}.csv

It writes compact derived CSV tables to:

  <benchmark-root>/derived_metrics/variant_metrics.csv
  <benchmark-root>/derived_metrics/runtime_phase_metrics.csv
  <benchmark-root>/derived_metrics/memory_phase_metrics.csv
  <benchmark-root>/derived_metrics/hardware_event_metrics.csv

The output is intentionally CSV-only so it can be inspected directly in CLion
and used as input for the final plotting script.
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
    "sorting",
    "reference_rebuild_container_update",
    "time_integration",
    "other",
]

MEMORY_PHASES = [
    "force_traversal",
    "verlet_construction",
]

MEMORY_TOP_DOWN_COLUMNS = {
    "memory_bound_percent": (
        "Memory Bound:Total(%)",
        "Memory Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:Self(%)",
    ),
    "l1_bound_percent": (
        "Memory Bound:L1 Bound:Total(%)",
        "Memory Bound:L1 Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:L1 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L1 Bound:Self(%)",
    ),
    "l2_bound_percent": (
        "Memory Bound:L2 Bound:Total(%)",
        "Memory Bound:L2 Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:L2 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L2 Bound:Self(%)",
    ),
    "l3_bound_percent": (
        "Memory Bound:L3 Bound:Total(%)",
        "Memory Bound:L3 Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:L3 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L3 Bound:Self(%)",
    ),
    "dram_bound_percent": (
        "Memory Bound:DRAM Bound:Total(%)",
        "Memory Bound:DRAM Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:DRAM Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:DRAM Bound:Self(%)",
    ),
    "store_bound_percent": (
        "Memory Bound:Store Bound:Total(%)",
        "Memory Bound:Store Bound:Self(%)",
        "Performance-core (P-core):Memory Bound:Store Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:Store Bound:Self(%)",
    ),
    "loads_percent": (
        "Loads:Total",
        "Loads:Self",
    ),
    "stores_percent": (
        "Stores:Total",
        "Stores:Self",
    ),
    "llc_miss_count_percent": (
        "LLC Miss Count:Total",
        "LLC Miss Count:Self",
    ),
    "average_latency_cycles": (
        "Average Latency (cycles):Total",
        "Average Latency (cycles):Self",
    ),
}

HARDWARE_EVENT_COLUMNS = {
    "attributed_inst_retired_any": "Hardware Event Count:INST_RETIRED.ANY",
    "attributed_cpu_clk_unhalted_thread": "Hardware Event Count:CPU_CLK_UNHALTED.THREAD",
    "attributed_mem_inst_retired_all_loads": "Hardware Event Count:MEM_INST_RETIRED.ALL_LOADS",
    "attributed_mem_inst_retired_all_stores": "Hardware Event Count:MEM_INST_RETIRED.ALL_STORES",
    "attributed_mem_load_retired_l1_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L1_HIT",
    "attributed_mem_load_retired_l1_miss": "Hardware Event Count:MEM_LOAD_RETIRED.L1_MISS",
    "attributed_mem_load_retired_l2_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L2_HIT",
    "attributed_mem_load_retired_l3_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L3_HIT",
    "attributed_mem_load_retired_l3_miss": "Hardware Event Count:MEM_LOAD_RETIRED.L3_MISS",
    "attributed_cycle_activity_stalls_l1d_miss": "Hardware Event Count:CYCLE_ACTIVITY.STALLS_L1D_MISS",
    "attributed_cycle_activity_stalls_l2_miss": "Hardware Event Count:CYCLE_ACTIVITY.STALLS_L2_MISS",
    "attributed_cycle_activity_stalls_l3_miss": "Hardware Event Count:CYCLE_ACTIVITY.STALLS_L3_MISS",
    "attributed_topdown_slots": "Hardware Event Count:TOPDOWN.SLOTS",
    "attributed_topdown_backend_bound_slots": "Hardware Event Count:TOPDOWN.BACKEND_BOUND_SLOTS",
}


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
        help="Scenario benchmark root, e.g. benchmarks/CoolMuc/homogeneous70.",
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
        help="Skip variants whose benchmark directory is missing. Existing but malformed files still fail.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a comma-separated VTune or runtime CSV file.

    VTune indents call-tree entries with spaces before quotes. skipinitialspace
    is therefore required, otherwise template commas inside function names shift
    subsequent columns.
    """

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames is None:
            raise RuntimeError(f"{path} is empty or has no CSV header")
        return list(reader)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing required file: {path}")


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


def format_float(value: float | None) -> str:
    if value is None:
        return ""
    if not math.isfinite(value):
        return ""
    return f"{value:.9f}"


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return numerator / denominator


def row_text(row: dict[str, str]) -> str:
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


def find_best_memory_row(rows: list[dict[str, str]], rule: MatchRule) -> dict[str, str] | None:
    """Find the matching memory row with the most usable memory metrics."""

    candidates: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        text = row_text(row)
        if not contains_all(text, rule.include) or not contains_none(text, rule.exclude):
            continue

        score = 0
        for column_names in MEMORY_TOP_DOWN_COLUMNS.values():
            if first_available_value(row, column_names) is not None:
                score += 1
        candidates.append((score, row))

    candidates = [candidate for candidate in candidates if candidate[0] > 0]
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    if rule.required:
        includes = ", ".join(rule.include)
        excludes = ", ".join(rule.exclude) if rule.exclude else "-"
        raise RuntimeError(f"Could not find memory VTune row for phase={rule.phase}, include=[{includes}], exclude=[{excludes}]")
    return None


def first_available_value(row: dict[str, str], column_names: Iterable[str]) -> float | None:
    for column_name in column_names:
        value = parse_float(row.get(column_name))
        if value is not None:
            return value
    return None


def require_top_down_value(row: dict[str, str], column_names: Iterable[str], context: str) -> float:
    value = first_available_value(row, column_names)
    if value is None:
        columns = ", ".join(column_names)
        raise RuntimeError(f"Missing required VTune top-down metric while reading {context}; checked columns: {columns}")
    return value


def top_down_value_or_zero(row: dict[str, str], column_names: Iterable[str]) -> float:
    """Read a VTune metric and interpret an omitted field as zero.

    VTune's top-down reports often leave zero-valued submetrics blank. Once a
    meaningful phase row has been found, these blanks are treated as zero rather
    than as missing data.
    """

    value = first_available_value(row, column_names)
    return value if value is not None else 0.0
    return value


def parse_variant_parts(variant: str) -> tuple[str, str]:
    if variant == "no-sorting":
        return "none", "none"
    resolution, order = variant.split("-", maxsplit=1)
    return resolution, order


def parse_yaml_metadata(input_yaml: Path) -> dict[str, str]:
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

    newton3 = ""
    newton3_match = re.search(r"newton3\s*:\s*\[([^\]]+)\]", text)
    if newton3_match:
        newton3 = newton3_match.group(1).strip()

    iterations = ""
    iterations_match = re.search(r"iterations\s*:\s*(\d+)", text)
    if iterations_match:
        iterations = iterations_match.group(1)

    return {
        "particle_count": particle_count,
        "data_layout": data_layout,
        "newton3": newton3,
        "iterations": iterations,
    }


def read_runtime_summary(runtimes_path: Path) -> dict[str, float | int]:
    rows = read_csv(runtimes_path)
    required_columns = {"run_id", "wall_clock_s", "output_file"}
    missing_columns = required_columns.difference(rows[0].keys() if rows else set())
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


def read_hotspots_cpu_time(summary_path: Path) -> float:
    rows = read_csv(summary_path)
    for row in rows:
        if row.get("Metric Name") == "CPU Time":
            value = parse_float(row.get("Metric Value"))
            if value is not None:
                return value
    raise RuntimeError(f"Could not find CPU Time in {summary_path}")


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
            exclude=(),
        ),
    )
    sorting_row = find_first_row(
        rows,
        MatchRule(
            phase="sorting",
            include=("sortParticlesByConfiguredKey",),
            exclude=(),
            required=False,
        ),
    )

    position_row = find_first_row(
        rows,
        MatchRule(
            phase="time_integration_position",
            include=("TimeDiscretization::calculatePositionsAndResetForces",),
            exclude=("_omp_fn",),
        ),
    )
    velocity_row = find_first_row(
        rows,
        MatchRule(
            phase="time_integration_velocity",
            include=("TimeDiscretization::calculateVelocities",),
            exclude=("_omp_fn",),
        ),
    )

    force = require_top_down_value(force_row, ("CPU Time:Total",), str(top_down_path))
    verlet = require_top_down_value(verlet_row, ("CPU Time:Total",), str(top_down_path))
    update_total = require_top_down_value(update_container_row, ("CPU Time:Total",), str(top_down_path))
    sorting = require_top_down_value(sorting_row, ("CPU Time:Total",), str(top_down_path)) if sorting_row is not None else 0.0
    position = require_top_down_value(position_row, ("CPU Time:Total",), str(top_down_path))
    velocity = require_top_down_value(velocity_row, ("CPU Time:Total",), str(top_down_path))

    reference_rebuild = max(update_total - sorting, 0.0)
    time_integration = position + velocity
    known_sum = force + verlet + sorting + reference_rebuild + time_integration
    other = max(100.0 - known_sum, 0.0)

    percentages = {
        "force_traversal": force,
        "verlet_construction": verlet,
        "sorting": sorting,
        "reference_rebuild_container_update": reference_rebuild,
        "time_integration": time_integration,
        "other": other,
    }
    matches = {
        "force_traversal": row_text(force_row),
        "verlet_construction": row_text(verlet_row),
        "sorting": row_text(sorting_row) if sorting_row is not None else "",
        "reference_rebuild_container_update": row_text(update_container_row),
        "time_integration": f"{row_text(position_row)} | {row_text(velocity_row)}",
        "other": "100 - selected runtime phases",
    }
    return percentages, matches


def extract_memory_phase_metrics(top_down_path: Path) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    rows = read_csv(top_down_path)
    phase_rules = {
        "force_traversal": MatchRule(
            phase="force_traversal",
            include=("VLListIterationTraversal", "traverseParticles"),
        ),
        "verlet_construction": MatchRule(
            phase="verlet_construction",
            include=("VerletListGeneratorFunctor", "SoAFunctor"),
        ),
    }

    metrics: dict[str, dict[str, float]] = {}
    matches: dict[str, str] = {}
    for phase, rule in phase_rules.items():
        row = find_best_memory_row(rows, rule)
        if row is None:
            raise RuntimeError(f"Could not extract memory phase {phase} from {top_down_path}")

        phase_metrics: dict[str, float] = {}
        for metric_name, column_names in MEMORY_TOP_DOWN_COLUMNS.items():
            phase_metrics[metric_name] = top_down_value_or_zero(row, column_names)

        metrics[phase] = phase_metrics
        matches[phase] = row_text(row)

    return metrics, matches


def extract_hardware_events(hw_events_path: Path) -> dict[str, float]:
    rows = read_csv(hw_events_path)
    if not rows:
        raise RuntimeError(f"{hw_events_path} contains no hardware event rows")

    missing_columns = [
        column_name
        for column_name in HARDWARE_EVENT_COLUMNS.values()
        if column_name not in rows[0]
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise RuntimeError(f"{hw_events_path} is missing required hardware event columns: {missing}")

    totals = {metric_name: 0.0 for metric_name in HARDWARE_EVENT_COLUMNS}
    for row in rows:
        for metric_name, column_name in HARDWARE_EVENT_COLUMNS.items():
            value = parse_float(row.get(column_name))
            if value is not None:
                totals[metric_name] += value

    loads = totals["attributed_mem_inst_retired_all_loads"]
    totals["attributed_l3_misses_per_load"] = safe_div(totals["attributed_mem_load_retired_l3_miss"], loads) or 0.0
    totals["attributed_l3_stalls_per_load"] = safe_div(totals["attributed_cycle_activity_stalls_l3_miss"], loads) or 0.0
    totals["attributed_l1_misses_per_load"] = safe_div(totals["attributed_mem_load_retired_l1_miss"], loads) or 0.0
    totals["attributed_l2_hits_per_load"] = safe_div(totals["attributed_mem_load_retired_l2_hit"], loads) or 0.0
    totals["attributed_l3_hits_per_load"] = safe_div(totals["attributed_mem_load_retired_l3_hit"], loads) or 0.0

    return totals


def build_tables(benchmark_root: Path, allow_missing: bool) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    variant_context: dict[str, dict[str, object]] = {}

    for variant in VARIANTS:
        variant_dir = benchmark_root / variant
        if not variant_dir.exists():
            if allow_missing:
                continue
            raise RuntimeError(f"Missing variant directory: {variant_dir}")

        input_yaml = benchmark_root / "inputs" / f"{variant}.yaml"
        runtimes_path = variant_dir / "runtime" / "runtimes.csv"
        hotspots_summary_path = variant_dir / "vtune_hotspots" / "summary.csv"
        hotspots_top_down_path = variant_dir / "vtune_hotspots" / "top_down.csv"
        memory_top_down_path = variant_dir / "vtune_memory" / "top_down.csv"
        hw_events_path = variant_dir / "vtune_memory" / "hw_events.csv"

        for path in (input_yaml, runtimes_path, hotspots_summary_path, hotspots_top_down_path, memory_top_down_path, hw_events_path):
            require_file(path)

        runtime_summary = read_runtime_summary(runtimes_path)
        hotspots_cpu_time_s = read_hotspots_cpu_time(hotspots_summary_path)
        phase_percentages, phase_matches = extract_runtime_phase_percentages(hotspots_top_down_path)
        memory_metrics, memory_matches = extract_memory_phase_metrics(memory_top_down_path)
        hardware_events = extract_hardware_events(hw_events_path)
        yaml_metadata = parse_yaml_metadata(input_yaml)

        variant_context[variant] = {
            "runtime_summary": runtime_summary,
            "hotspots_cpu_time_s": hotspots_cpu_time_s,
            "phase_percentages": phase_percentages,
            "phase_matches": phase_matches,
            "memory_metrics": memory_metrics,
            "memory_matches": memory_matches,
            "hardware_events": hardware_events,
            "yaml_metadata": yaml_metadata,
        }

    if not variant_context:
        raise RuntimeError(f"No variants found under {benchmark_root}")

    baseline_context = variant_context.get("no-sorting")
    if baseline_context is None:
        raise RuntimeError("The no-sorting baseline is required to calculate speedups")

    baseline_runtime = baseline_context["runtime_summary"]["mean_wall_clock_s"]  # type: ignore[index]
    if not isinstance(baseline_runtime, float):
        raise RuntimeError("Internal error: baseline runtime was not parsed as float")

    variant_rows: list[dict[str, str]] = []
    runtime_phase_rows: list[dict[str, str]] = []
    memory_phase_rows: list[dict[str, str]] = []
    hardware_event_rows: list[dict[str, str]] = []

    for variant in VARIANTS:
        if variant not in variant_context:
            continue

        context = variant_context[variant]
        runtime_summary = context["runtime_summary"]  # type: ignore[assignment]
        hotspots_cpu_time_s = context["hotspots_cpu_time_s"]  # type: ignore[assignment]
        phase_percentages = context["phase_percentages"]  # type: ignore[assignment]
        memory_metrics = context["memory_metrics"]  # type: ignore[assignment]
        hardware_events = context["hardware_events"]  # type: ignore[assignment]
        yaml_metadata = context["yaml_metadata"]  # type: ignore[assignment]
        resolution, order = parse_variant_parts(variant)

        assert isinstance(runtime_summary, dict)
        assert isinstance(hotspots_cpu_time_s, float)
        assert isinstance(phase_percentages, dict)
        assert isinstance(memory_metrics, dict)
        assert isinstance(hardware_events, dict)
        assert isinstance(yaml_metadata, dict)

        mean_runtime = runtime_summary["mean_wall_clock_s"]
        assert isinstance(mean_runtime, float)
        speedup = safe_div(baseline_runtime, mean_runtime)

        variant_row = {
            "scenario": benchmark_root.name,
            "variant": variant,
            "sorting_resolution": resolution,
            "sorting_order": order,
            "data_layout": str(yaml_metadata["data_layout"]),
            "newton3": str(yaml_metadata["newton3"]),
            "iterations": str(yaml_metadata["iterations"]),
            "particle_count": str(yaml_metadata["particle_count"]),
            "runs": str(runtime_summary["runs"]),
            "mean_wall_clock_s": format_float(mean_runtime),
            "min_wall_clock_s": format_float(runtime_summary["min_wall_clock_s"]),  # type: ignore[arg-type]
            "max_wall_clock_s": format_float(runtime_summary["max_wall_clock_s"]),  # type: ignore[arg-type]
            "stddev_wall_clock_s": format_float(runtime_summary["stddev_wall_clock_s"]),  # type: ignore[arg-type]
            "speedup_vs_no_sorting": format_float(speedup),
            "hotspots_cpu_time_s": format_float(hotspots_cpu_time_s),
        }

        for phase in RUNTIME_PHASES:
            percentage = phase_percentages[phase]
            assert isinstance(percentage, float)
            variant_row[f"phase_{phase}_percent"] = format_float(percentage)
            variant_row[f"phase_{phase}_cpu_time_s_estimate"] = format_float(hotspots_cpu_time_s * percentage / 100.0)

            runtime_phase_rows.append(
                {
                    "scenario": benchmark_root.name,
                    "variant": variant,
                    "phase": phase,
                    "cpu_time_percent": format_float(percentage),
                    "cpu_time_s_estimate": format_float(hotspots_cpu_time_s * percentage / 100.0),
                    "source_match": str(context["phase_matches"][phase]),  # type: ignore[index]
                }
            )

        for phase in MEMORY_PHASES:
            phase_metrics = memory_metrics[phase]
            assert isinstance(phase_metrics, dict)
            for metric_name, value in phase_metrics.items():
                assert isinstance(value, float)
                variant_row[f"memory_{phase}_{metric_name}"] = format_float(value)

            memory_phase_rows.append(
                {
                    "scenario": benchmark_root.name,
                    "variant": variant,
                    "phase": phase,
                    **{metric_name: format_float(value) for metric_name, value in phase_metrics.items()},
                    "source_match": str(context["memory_matches"][phase]),  # type: ignore[index]
                }
            )

        hardware_event_row = {
            "scenario": benchmark_root.name,
            "variant": variant,
            "sorting_resolution": resolution,
            "sorting_order": order,
        }
        for metric_name, value in hardware_events.items():
            assert isinstance(value, float)
            hardware_event_row[metric_name] = format_float(value)
            variant_row[metric_name] = format_float(value)

        hardware_event_rows.append(hardware_event_row)
        variant_rows.append(variant_row)

    return variant_rows, runtime_phase_rows, memory_phase_rows, hardware_event_rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows to write for {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    benchmark_root = args.benchmark_root
    output_dir = args.output_dir or benchmark_root / "derived_metrics"

    variant_rows, runtime_phase_rows, memory_phase_rows, hardware_event_rows = build_tables(
        benchmark_root, args.allow_missing
    )

    write_csv(output_dir / "variant_metrics.csv", variant_rows)
    write_csv(output_dir / "runtime_phase_metrics.csv", runtime_phase_rows)
    write_csv(output_dir / "memory_phase_metrics.csv", memory_phase_rows)
    write_csv(output_dir / "hardware_event_metrics.csv", hardware_event_rows)

    print(f"Wrote {output_dir / 'variant_metrics.csv'}")
    print(f"Wrote {output_dir / 'runtime_phase_metrics.csv'}")
    print(f"Wrote {output_dir / 'memory_phase_metrics.csv'}")
    print(f"Wrote {output_dir / 'hardware_event_metrics.csv'}")


if __name__ == "__main__":
    main()
