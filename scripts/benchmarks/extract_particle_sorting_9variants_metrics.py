#!/usr/bin/env python3
"""Extract derived benchmark metrics for the particle-sorting 9-variant run.

The script reads the raw Hyperfine and VTune CSV files from one benchmark
directory and writes two derived tables:

* derived_metrics/variant_metrics.csv
* derived_metrics/function_group_metrics.csv

The function groups are intentionally fixed for this benchmark family:
VerletListsReferences, AoS, vl_list_iteration, Newton3 disabled, homogeneous
cube grid. If the benchmark family changes, review the grouping rules before
reusing the generated function-group table.
"""

from __future__ import annotations

import argparse
import csv
import re
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

FUNCTION_GROUPS = [
    "force_traversal",
    "verlet_construction",
    "sorting_key_generation",
    "reference_rebuild_container_update",
    "time_integration",
    "bookkeeping",
    "other",
]

PHASES = [
    "force_traversal",
    "verlet_construction",
    "sorting",
    "reference_rebuild_container_update",
    "time_integration",
    "other",
]

MEMORY_TOP_DOWN_PHASES = [
    "force_traversal",
    "verlet_construction",
]

EVENT_COLUMNS = {
    "mem_load_retired_l1_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L1_HIT",
    "mem_load_retired_l1_miss": "Hardware Event Count:MEM_LOAD_RETIRED.L1_MISS",
    "mem_load_retired_l2_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L2_HIT",
    "mem_load_retired_l3_hit": "Hardware Event Count:MEM_LOAD_RETIRED.L3_HIT",
    "mem_load_retired_l3_miss": "Hardware Event Count:MEM_LOAD_RETIRED.L3_MISS",
    "mem_inst_retired_all_loads": "Hardware Event Count:MEM_INST_RETIRED.ALL_LOADS",
    "mem_inst_retired_all_stores": "Hardware Event Count:MEM_INST_RETIRED.ALL_STORES",
    "topdown_memory_bound_slots": "Hardware Event Count:TOPDOWN.MEMORY_BOUND_SLOTS",
    "memory_activity_stalls_l1d_miss": "Hardware Event Count:MEMORY_ACTIVITY.STALLS_L1D_MISS",
    "memory_activity_stalls_l2_miss": "Hardware Event Count:MEMORY_ACTIVITY.STALLS_L2_MISS",
    "memory_activity_stalls_l3_miss": "Hardware Event Count:MEMORY_ACTIVITY.STALLS_L3_MISS",
}

MEMORY_TOP_DOWN_COLUMNS = {
    "memory_bound_percent": (
        "Performance-core (P-core):Memory Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:Self(%)",
    ),
    "l1_bound_percent": (
        "Performance-core (P-core):Memory Bound:L1 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L1 Bound:Self(%)",
    ),
    "l2_bound_percent": (
        "Performance-core (P-core):Memory Bound:L2 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L2 Bound:Self(%)",
    ),
    "l3_bound_percent": (
        "Performance-core (P-core):Memory Bound:L3 Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:L3 Bound:Self(%)",
    ),
    "dram_bound_percent": (
        "Performance-core (P-core):Memory Bound:DRAM Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:DRAM Bound:Self(%)",
    ),
    "store_bound_percent": (
        "Performance-core (P-core):Memory Bound:Store Bound:Total(%)",
        "Performance-core (P-core):Memory Bound:Store Bound:Self(%)",
    ),
    "average_latency_cycles": (
        "Average Latency (cycles):Total",
        "Average Latency (cycles):Self",
    ),
}


@dataclass(frozen=True)
class FunctionRow:
    """Minimal function identity used for grouping rows from VTune exports."""

    function: str
    full_function: str
    source_file: str

    @property
    def text(self) -> str:
        return f"{self.function} {self.full_function} {self.source_file}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=Path("benchmarks/particle-sorting-9variants"),
        help="Root directory containing inputs and per-variant benchmark outputs.",
    )
    return parser.parse_args()


def read_csv(path: Path, delimiter: str | None = None) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        if delimiter is None:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
            except csv.Error:
                delimiter = ","
        return list(csv.DictReader(handle, delimiter=delimiter, skipinitialspace=True))


def as_float(value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def parse_variant_parts(variant: str) -> tuple[str, str]:
    if variant == "no-sorting":
        return "none", "none"
    resolution, order = variant.split("-", maxsplit=1)
    return resolution, order


def parse_particle_count(input_yaml: Path) -> int:
    text = input_yaml.read_text()
    match = re.search(r"particles-per-dimension\s*:\s*\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]", text)
    if not match:
        return 0
    x, y, z = (int(value) for value in match.groups())
    return x * y * z


def make_function_row(row: dict[str, str]) -> FunctionRow:
    return FunctionRow(
        function=row.get("Function", ""),
        full_function=row.get("Function (Full)", ""),
        source_file=row.get("Source File", ""),
    )


def contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def classify_function(row: FunctionRow) -> str:
    """Map a VTune function row to one fixed benchmark-specific group."""

    text = row.text

    # Sorting and key generation are optimization overhead. The top-down VTune
    # reports show std::sort below sortParticlesByConfiguredKey for the current
    # benchmark family, so the STL sort internals are counted here.
    if contains_any(
        text,
        [
            "sortParticlesByConfiguredKey",
            "sortParticlesAndUpdateReferences",
            "ParticleVector<mdLib::MoleculeLJ>::sortParticles",
            "sortingKeyForParticle",
            "linearKey",
            "mortonKey",
            "hilbertKey",
            "hilbertAxesToTranspose",
            "getCellCoordinateForPosition",
            "getBlockCoordinateForPosition",
            "getParticleCoordinateForPosition",
            "std::sort",
            "__sort",
            "__introsort",
            "__insertion_sort",
        ],
    ):
        return "sorting_key_generation"

    # Neighbor-list construction uses the LinkedCellsReferences backend with an
    # LCC08 traversal to build the AoS Verlet lists before force traversal.
    if contains_any(
        text,
        [
            "LinkedCellsReferences<mdLib::MoleculeLJ>::computeInteractions",
            "VerletListGeneratorFunctor",
            "generateAoSNeighborLists",
            "LCC08Traversal",
            "C08Traversal",
            "ColorBasedTraversal",
            "CellFunctor",
        ],
    ):
        return "verlet_construction"

    # Force traversal is the main locality-sensitive work. It iterates over the
    # already-built AoS neighbor lists and applies the Lennard-Jones functor.
    if contains_any(
        text,
        [
            "VLListIterationTraversal",
            "AoSFunctor",
            "LJFunctorAVX",
            "ArrayMath::dot",
            "ArrayMath::sub",
            "ArrayMath::mulScalar",
            "ArrayMath::literals::operator+=",
            "ParticlePropertiesLibrary",
            "MoleculeLJ::getTypeId",
        ],
    ):
        return "force_traversal"

    # Reference rebuild and update work is specific to the LinkedCellsReferences
    # backend. Avoid broad class-name matching here: computeInteractions belongs
    # to Verlet-list construction in this benchmark family.
    if contains_any(
        text,
        [
            "updateDirtyParticleReferences",
            "LinkedCellsReferences<mdLib::MoleculeLJ>::updateContainer",
            "VerletListsLinkedReferencesBase<mdLib::MoleculeLJ>::updateContainer",
            "ReferenceParticleCell",
            "LeavingParticleCollector",
            "collectParticlesAndMarkNonOwnedAsDummy",
            "advanceIteratorIndices",
            "getParticleImpl",
            "getParticle(",
            "particleFulfillsIteratorRequirements",
        ],
    ):
        return "reference_rebuild_container_update"

    if contains_any(
        text,
        [
            "TimeDiscretization::calculatePositionsAndResetForces",
            "TimeDiscretization::calculateVelocities",
            "MoleculeLJ::setF",
            "MoleculeLJ::setOldF",
        ],
    ):
        return "time_integration"

    # STL/hash/vector/allocator functions support the algorithm but are not
    # direct proof of particle data locality.
    if contains_any(
        text,
        [
            "std::unordered_map",
            "std::vector",
            "operator new",
            "operator delete",
            "allocator",
            "stl_vector",
            "unordered_map.h",
        ],
    ):
        return "bookkeeping"

    return "other"


def read_hyperfine_metrics(variant_dir: Path) -> dict[str, float]:
    rows = read_csv(variant_dir / "runtime" / "hyperfine.csv")
    if len(rows) != 1:
        raise RuntimeError(f"Expected one hyperfine row in {variant_dir}")
    row = rows[0]
    return {
        "runtime_mean_s": as_float(row["mean"]),
        "runtime_stddev_s": as_float(row["stddev"]),
        "runtime_min_s": as_float(row["min"]),
        "runtime_max_s": as_float(row["max"]),
    }


def aggregate_hotspot_cpu_by_group(variant_dir: Path) -> dict[str, float]:
    groups = {group: 0.0 for group in FUNCTION_GROUPS}
    for row in read_csv(variant_dir / "vtune_hotspots" / "functions.csv"):
        group = classify_function(make_function_row(row))
        groups[group] += as_float(row.get("CPU Time"))
    return groups


def aggregate_memory_events_by_group(variant_dir: Path) -> dict[str, dict[str, float]]:
    groups = {group: {event: 0.0 for event in EVENT_COLUMNS} for group in FUNCTION_GROUPS}
    hw_events_path = variant_dir / "vtune_memory" / "hw_events.csv"
    if not hw_events_path.exists():
        raise RuntimeError(f"Missing VTune memory hardware-events report: {hw_events_path}")
    if hw_events_path.stat().st_size == 0:
        raise RuntimeError(f"Empty VTune memory hardware-events report: {hw_events_path}")

    for row in read_csv(hw_events_path):
        group = classify_function(make_function_row(row))
        for event_name, column_name in EVENT_COLUMNS.items():
            groups[group][event_name] += as_float(row.get(column_name))
    return groups


def has_memory_events(variant_dir: Path) -> str:
    hw_events_path = variant_dir / "vtune_memory" / "hw_events.csv"
    return str(hw_events_path.exists() and hw_events_path.stat().st_size > 0).lower()


def top_down_function_text(row: dict[str, str]) -> str:
    """Return the available function identity fields from a VTune top-down row."""

    return " ".join(
        [
            row.get("Function Stack", ""),
            row.get("Function", ""),
            row.get("Function (Full)", ""),
            row.get("Source File", ""),
        ]
    )


def max_top_down_total(rows: list[dict[str, str]], required_needles: Iterable[str]) -> float:
    """Find the largest inclusive top-down percentage matching all needles.

    VTune's top-down report is hierarchical: a parent row includes the time of
    all children below it. Taking the maximum matching inclusive value gives the
    phase-level cost for a call path such as sortParticlesByConfiguredKey(),
    instead of only the self-time of the leaf encoding functions.
    """

    needles = tuple(required_needles)
    return max(
        (
            as_float(row.get("CPU Time:Total"))
            for row in rows
            if all(needle in top_down_function_text(row) for needle in needles)
        ),
        default=0.0,
    )


def top_down_row_value(row: dict[str, str], total_column: str, self_column: str, context: str) -> float:
    """Read a top-down metric, falling back from Total to Self if needed."""

    if total_column not in row:
        raise RuntimeError(f"Missing required VTune top-down column {total_column!r} while reading {context}")
    if self_column not in row:
        raise RuntimeError(f"Missing required VTune top-down fallback column {self_column!r} while reading {context}")

    total_value = row.get(total_column)
    if total_value not in (None, ""):
        return as_float(total_value)

    self_value = row.get(self_column)
    if self_value not in (None, ""):
        return as_float(self_value)

    raise RuntimeError(
        f"Missing required VTune top-down metric while reading {context}: "
        f"both {total_column!r} and {self_column!r} are empty"
    )


def max_matching_top_down_row(
    rows: list[dict[str, str]], required_needles: Iterable[str]
) -> dict[str, str] | None:
    """Return the matching row with the largest inclusive CPU-time percentage."""

    needles = tuple(required_needles)
    matching_rows = [
        row for row in rows if all(needle in top_down_function_text(row) for needle in needles)
    ]
    if not matching_rows:
        return None
    return max(matching_rows, key=lambda row: as_float(row.get("CPU Time:Total")))


def extract_top_down_phase_percentages(variant_dir: Path) -> dict[str, float]:
    """Extract non-overlapping phase percentages from VTune top-down output.

    The top-down CSV reports inclusive percentages. For example,
    updateContainer() includes sorting if sorting is enabled. Therefore the
    non-overlapping update/reference phase is computed as:

    updateContainer total - sortParticlesByConfiguredKey total
    """

    percentages = {phase: 0.0 for phase in PHASES}
    percentages["container_update_total"] = 0.0
    path = variant_dir / "vtune_hotspots" / "top_down.csv"
    if not path.exists():
        return percentages

    rows = read_csv(path)
    force = max_top_down_total(rows, ["VLListIterationTraversal", "traverseParticles"])
    construction = max_top_down_total(rows, ["LinkedCellsReferences<mdLib::MoleculeLJ>::computeInteractions"])
    sorting = max_top_down_total(rows, ["sortParticlesByConfiguredKey"])
    container_update_total = max_top_down_total(
        rows, ["VerletListsLinkedReferencesBase<mdLib::MoleculeLJ>::updateContainer"]
    )
    position_update = max_top_down_total(rows, ["TimeDiscretization::calculatePositionsAndResetForces"])
    velocity_update = max_top_down_total(rows, ["TimeDiscretization::calculateVelocities"])

    reference_update_without_sorting = max(container_update_total - sorting, 0.0)
    time_integration = position_update + velocity_update

    percentages["force_traversal"] = force
    percentages["verlet_construction"] = construction
    percentages["sorting"] = sorting
    percentages["reference_rebuild_container_update"] = reference_update_without_sorting
    percentages["time_integration"] = time_integration
    percentages["container_update_total"] = container_update_total

    accounted = force + construction + sorting + reference_update_without_sorting + time_integration
    percentages["other"] = max(100.0 - accounted, 0.0)
    return percentages


def extract_memory_top_down_phase_metrics(variant_dir: Path) -> dict[str, float]:
    """Extract memory top-down metrics for the main particle-access phases."""

    path = variant_dir / "vtune_memory" / "top_down.csv"
    if not path.exists():
        raise RuntimeError(f"Missing VTune memory top-down report: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Empty VTune memory top-down report: {path}")

    rows = read_csv(path)
    phase_needles = {
        "force_traversal": ["VLListIterationTraversal", "traverseParticles"],
        "verlet_construction": ["VerletListGeneratorFunctor::SoAFunctorPair"],
    }

    metrics = {
        f"memory_topdown_{phase}_{metric_name}": 0.0
        for phase in MEMORY_TOP_DOWN_PHASES
        for metric_name in MEMORY_TOP_DOWN_COLUMNS
    }

    for phase, needles in phase_needles.items():
        row = max_matching_top_down_row(rows, needles)
        if row is None:
            raise RuntimeError(f"Could not find VTune memory top-down phase {phase!r} in {path}")
        for metric_name, (total_column, self_column) in MEMORY_TOP_DOWN_COLUMNS.items():
            context = f"{path}, phase={phase}, metric={metric_name}"
            metrics[f"memory_topdown_{phase}_{metric_name}"] = top_down_row_value(
                row, total_column, self_column, context
            )

    return metrics


def phase_time_estimates(phase_percentages: dict[str, float], total_cpu_time_s: float) -> dict[str, float]:
    """Convert top-down percentages to estimated seconds using total flat CPU time."""

    estimates = {
        f"phase_{phase}_cpu_time_s_estimate": phase_percentages[phase] / 100.0 * total_cpu_time_s
        for phase in PHASES
    }
    estimates["phase_container_update_total_cpu_time_s_estimate"] = (
        phase_percentages["container_update_total"] / 100.0 * total_cpu_time_s
    )
    return estimates


def sum_group_events(group_events: dict[str, dict[str, float]]) -> dict[str, float]:
    totals = {event: 0.0 for event in EVENT_COLUMNS}
    for events in group_events.values():
        for event_name, value in events.items():
            totals[event_name] += value
    return totals


def add_derived_memory_metrics(row: dict[str, float | str]) -> None:
    loads = float(row.get("mem_inst_retired_all_loads", 0.0))
    cpu_time = float(row.get("cpu_time_s", 0.0) or row.get("hotspots_grouped_cpu_time_s", 0.0))
    row["l1_miss_per_load"] = safe_div(float(row.get("mem_load_retired_l1_miss", 0.0)), loads)
    row["l3_miss_per_load"] = safe_div(float(row.get("mem_load_retired_l3_miss", 0.0)), loads)
    row["l3_stalls_per_load"] = safe_div(float(row.get("memory_activity_stalls_l3_miss", 0.0)), loads)
    row["l3_stalls_per_cpu_second"] = safe_div(float(row.get("memory_activity_stalls_l3_miss", 0.0)), cpu_time)
    row["memory_bound_slots_per_cpu_second"] = safe_div(float(row.get("topdown_memory_bound_slots", 0.0)), cpu_time)


def write_csv(path: Path, rows: list[dict[str, float | str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_tables(root: Path) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    scenario = root.name
    particle_count = parse_particle_count(root / "inputs" / "no-sorting.yaml")

    variant_intermediate: dict[str, dict[str, object]] = {}

    for variant in VARIANTS:
        variant_dir = root / variant
        if not variant_dir.exists():
            raise RuntimeError(f"Missing variant directory: {variant_dir}")
        cpu_by_group = aggregate_hotspot_cpu_by_group(variant_dir)
        memory_by_group = aggregate_memory_events_by_group(variant_dir)
        phase_percentages = extract_top_down_phase_percentages(variant_dir)
        memory_top_down_metrics = extract_memory_top_down_phase_metrics(variant_dir)
        variant_intermediate[variant] = {
            "runtime": read_hyperfine_metrics(variant_dir),
            "cpu_by_group": cpu_by_group,
            "memory_by_group": memory_by_group,
            "memory_total": sum_group_events(memory_by_group),
            "memory_events_available": has_memory_events(variant_dir),
            "phase_percentages": phase_percentages,
            "memory_top_down_metrics": memory_top_down_metrics,
        }

    baseline_runtime = variant_intermediate["no-sorting"]["runtime"]["runtime_mean_s"]  # type: ignore[index]
    baseline_cpu_by_group = variant_intermediate["no-sorting"]["cpu_by_group"]  # type: ignore[assignment]

    variant_rows: list[dict[str, float | str]] = []
    function_group_rows: list[dict[str, float | str]] = []

    for variant in VARIANTS:
        resolution, order = parse_variant_parts(variant)
        data = variant_intermediate[variant]
        runtime = data["runtime"]  # type: ignore[assignment]
        cpu_by_group = data["cpu_by_group"]  # type: ignore[assignment]
        memory_by_group = data["memory_by_group"]  # type: ignore[assignment]
        memory_total = data["memory_total"]  # type: ignore[assignment]
        memory_events_available = data["memory_events_available"]  # type: ignore[assignment]
        phase_percentages = data["phase_percentages"]  # type: ignore[assignment]
        memory_top_down_metrics = data["memory_top_down_metrics"]  # type: ignore[assignment]

        hotspots_cpu_time = sum(cpu_by_group.values())  # type: ignore[union-attr]
        sorting_cpu = cpu_by_group["sorting_key_generation"]  # type: ignore[index]
        force_cpu = cpu_by_group["force_traversal"]  # type: ignore[index]
        construction_cpu = cpu_by_group["verlet_construction"]  # type: ignore[index]
        phase_times = phase_time_estimates(phase_percentages, hotspots_cpu_time)  # type: ignore[arg-type]

        variant_row: dict[str, float | str] = {
            "scenario": scenario,
            "particle_count": particle_count,
            "variant": variant,
            "resolution": resolution,
            "order": order,
            "memory_events_available": memory_events_available,  # type: ignore[dict-item]
            **runtime,  # type: ignore[arg-type]
            "runtime_relative_to_baseline": safe_div(runtime["runtime_mean_s"], baseline_runtime),  # type: ignore[index]
            "speedup_percent": (baseline_runtime - runtime["runtime_mean_s"]) / baseline_runtime * 100.0,  # type: ignore[index]
            "hotspots_grouped_cpu_time_s": hotspots_cpu_time,
            "force_traversal_cpu_time_s": force_cpu,
            "verlet_construction_cpu_time_s": construction_cpu,
            "sorting_key_generation_cpu_time_s": sorting_cpu,
            "reference_rebuild_container_update_cpu_time_s": cpu_by_group["reference_rebuild_container_update"],  # type: ignore[index]
            "time_integration_cpu_time_s": cpu_by_group["time_integration"],  # type: ignore[index]
            "bookkeeping_cpu_time_s": cpu_by_group["bookkeeping"],  # type: ignore[index]
            "other_cpu_time_s": cpu_by_group["other"],  # type: ignore[index]
            "flat_sorting_self_time_fraction": safe_div(sorting_cpu, hotspots_cpu_time),
            "phase_sorting_fraction": safe_div(phase_percentages["sorting"], 100.0),  # type: ignore[index]
            "force_traversal_relative_to_baseline": safe_div(force_cpu, baseline_cpu_by_group["force_traversal"]),  # type: ignore[index]
            "verlet_construction_relative_to_baseline": safe_div(
                construction_cpu, baseline_cpu_by_group["verlet_construction"]  # type: ignore[index]
            ),
        }
        for phase in PHASES:
            variant_row[f"phase_{phase}_percent"] = phase_percentages[phase]  # type: ignore[index]
        variant_row["phase_container_update_total_percent"] = phase_percentages["container_update_total"]  # type: ignore[index]
        variant_row.update(phase_times)
        variant_row.update(memory_top_down_metrics)  # type: ignore[arg-type]
        variant_row.update(memory_total)  # type: ignore[arg-type]
        add_derived_memory_metrics(variant_row)
        variant_rows.append(variant_row)

        for group in FUNCTION_GROUPS:
            group_cpu = cpu_by_group[group]  # type: ignore[index]
            group_row: dict[str, float | str] = {
                "scenario": scenario,
                "particle_count": particle_count,
                "variant": variant,
                "resolution": resolution,
                "order": order,
                "function_group": group,
                "cpu_time_s": group_cpu,
                "cpu_time_fraction": safe_div(group_cpu, hotspots_cpu_time),
                "cpu_time_relative_to_baseline": safe_div(group_cpu, baseline_cpu_by_group[group]),  # type: ignore[index]
            }
            group_row.update(memory_by_group[group])  # type: ignore[index,arg-type]
            add_derived_memory_metrics(group_row)
            function_group_rows.append(group_row)

    return variant_rows, function_group_rows


def main() -> None:
    args = parse_args()
    root = args.benchmark_root
    derived_dir = root / "derived_metrics"

    variant_rows, function_group_rows = build_tables(root)

    variant_fields = [
        "scenario",
        "particle_count",
        "variant",
        "resolution",
        "order",
        "memory_events_available",
        "runtime_mean_s",
        "runtime_stddev_s",
        "runtime_min_s",
        "runtime_max_s",
        "runtime_relative_to_baseline",
        "speedup_percent",
        "hotspots_grouped_cpu_time_s",
        "force_traversal_cpu_time_s",
        "force_traversal_relative_to_baseline",
        "verlet_construction_cpu_time_s",
        "verlet_construction_relative_to_baseline",
        "sorting_key_generation_cpu_time_s",
        "flat_sorting_self_time_fraction",
        "phase_sorting_fraction",
        "reference_rebuild_container_update_cpu_time_s",
        "time_integration_cpu_time_s",
        "bookkeeping_cpu_time_s",
        "other_cpu_time_s",
        "phase_force_traversal_percent",
        "phase_force_traversal_cpu_time_s_estimate",
        "phase_verlet_construction_percent",
        "phase_verlet_construction_cpu_time_s_estimate",
        "phase_sorting_percent",
        "phase_sorting_cpu_time_s_estimate",
        "phase_reference_rebuild_container_update_percent",
        "phase_reference_rebuild_container_update_cpu_time_s_estimate",
        "phase_time_integration_percent",
        "phase_time_integration_cpu_time_s_estimate",
        "phase_other_percent",
        "phase_other_cpu_time_s_estimate",
        "phase_container_update_total_percent",
        "phase_container_update_total_cpu_time_s_estimate",
        *[
            f"memory_topdown_{phase}_{metric_name}"
            for phase in MEMORY_TOP_DOWN_PHASES
            for metric_name in MEMORY_TOP_DOWN_COLUMNS
        ],
        *EVENT_COLUMNS.keys(),
        "l1_miss_per_load",
        "l3_miss_per_load",
        "l3_stalls_per_load",
        "l3_stalls_per_cpu_second",
        "memory_bound_slots_per_cpu_second",
    ]

    function_group_fields = [
        "scenario",
        "particle_count",
        "variant",
        "resolution",
        "order",
        "function_group",
        "cpu_time_s",
        "cpu_time_fraction",
        "cpu_time_relative_to_baseline",
        *EVENT_COLUMNS.keys(),
        "l1_miss_per_load",
        "l3_miss_per_load",
        "l3_stalls_per_load",
        "l3_stalls_per_cpu_second",
        "memory_bound_slots_per_cpu_second",
    ]

    write_csv(derived_dir / "variant_metrics.csv", variant_rows, variant_fields)
    write_csv(derived_dir / "function_group_metrics.csv", function_group_rows, function_group_fields)

    print(f"Wrote {derived_dir / 'variant_metrics.csv'}")
    print(f"Wrote {derived_dir / 'function_group_metrics.csv'}")


if __name__ == "__main__":
    main()
