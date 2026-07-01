#!/usr/bin/env python3
"""Compare V4 reservation/round-two repair against V3 and V2.2."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Case:
    name: str
    legal: bool
    runtime: float
    wait: float
    memory: float
    finish: float
    selected: str
    candidates: str


def read_cases(path: Path) -> dict[str, Case]:
    cases: dict[str, Case] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            case = Case(
                row["case"],
                row["is_legal"].strip().lower() in {"1", "true"},
                float(row["elapsed_sec"]),
                float(row["E_wait"]),
                float(row["E_memory_new"]),
                float(row["E_finish"]),
                row.get("selected_config", "").strip(),
                row.get("valid_candidates", "").strip(),
            )
            cases[case.name] = case
    return cases


def aggregate(cases: dict[str, Case]) -> dict[str, float]:
    legal = [case for case in cases.values() if case.legal]
    return {
        "legal": len(legal),
        "count": len(cases),
        "wait": sum(case.wait for case in legal) / len(legal),
        "memory": sum(case.memory for case in legal) / len(legal),
        "finish": sum(case.finish for case in legal) / len(legal),
        "max_runtime": max(case.runtime for case in cases.values()),
        "case100": cases["case100.in"].runtime,
    }


def compare(old: dict[str, Case], new: dict[str, Case]) -> tuple[int, int, int]:
    improved = regressed = mixed = 0
    for name in sorted(set(old) & set(new)):
        deltas = (
            new[name].wait - old[name].wait,
            new[name].memory - old[name].memory,
            new[name].finish - old[name].finish,
        )
        if all(delta <= 0 for delta in deltas) and any(delta < 0 for delta in deltas):
            improved += 1
        elif all(delta >= 0 for delta in deltas) and any(delta > 0 for delta in deltas):
            regressed += 1
        else:
            mixed += 1
    return improved, regressed, mixed


def composite(old: dict[str, float], new: dict[str, float]) -> float:
    return 100.0 * sum(
        new[field] / old[field] - 1.0
        for field in ("wait", "memory", "finish")
    ) / 3.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v22", type=Path, required=True)
    parser.add_argument("--v3", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selections", type=Path, required=True)
    args = parser.parse_args()

    versions = {
        "V2.2": read_cases(args.v22),
        "V3": read_cases(args.v3),
        "V4": read_cases(args.v4),
    }
    stats = {name: aggregate(cases) for name, cases in versions.items()}
    versus_v3 = compare(versions["V3"], versions["V4"])
    versus_v22 = compare(versions["V2.2"], versions["V4"])
    counts = Counter(case.selected for case in versions["V4"].values())
    expected = {
        "v3_baseline",
        "repair_memory_round2",
        "repair_combo_round2",
        "repair_wait_memory_round2",
        "reservation_backfill",
        "reservation_repair_combo",
    }
    all_valid = sum(
        set(case.candidates.split(",")) == expected
        for case in versions["V4"].values()
    )
    reservation_cases = sorted(
        case.name for case in versions["V4"].values()
        if case.selected.startswith("reservation_")
    )
    round2_cases = sorted(
        case.name for case in versions["V4"].values()
        if "round2" in case.selected
    )

    lines = [
        "# V4 Reservation-aware Backfilling + Multi-round Repair",
        "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime (s) | case100 (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("V2.2", "V3", "V4"):
        item = stats[name]
        lines.append(
            f"| {name} | {item['legal']}/{item['count']} | {item['wait']:.2f} | "
            f"{item['memory']:.2f} | {item['finish']:.2f} | "
            f"{item['max_runtime']:.6f} | {item['case100']:.6f} |"
        )
    lines += [
        "",
        f"Composite change vs V3: {composite(stats['V3'], stats['V4']):+.6f}% (lower is better).",
        f"Composite change vs V2.2: {composite(stats['V2.2'], stats['V4']):+.6f}% (lower is better).",
        f"Strict improved/regressed/mixed vs V3: {versus_v3[0]}/{versus_v3[1]}/{versus_v3[2]}.",
        f"Strict improved/regressed/mixed vs V2.2: {versus_v22[0]}/{versus_v22[1]}/{versus_v22[2]}.",
        f"All six V4 candidates validated in {all_valid}/{len(versions['V4'])} cases.",
        "",
        "## Candidate Selection Counts",
        "",
    ]
    for name in sorted(expected):
        lines.append(f"- {name}: {counts.get(name, 0)}")
    lines += [
        "",
        "Reservation-selected cases: " + (", ".join(reservation_cases) or "none") + ".",
        "",
        "Multi-round-repair-selected cases: " + (", ".join(round2_cases) or "none") + ".",
        "",
    ]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    with args.selections.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["case", "selected_candidate", "E_wait", "E_memory_new", "E_finish", "runtime_sec"])
        for name in sorted(versions["V4"]):
            case = versions["V4"][name]
            writer.writerow([case.name, case.selected, case.wait, case.memory, case.finish, case.runtime])
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
