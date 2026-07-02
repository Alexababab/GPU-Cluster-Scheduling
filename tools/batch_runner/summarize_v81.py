#!/usr/bin/env python3
"""Summarize the guarded V8.1 emergency skeleton experiment."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


METRICS = ("E_wait", "E_memory_new", "E_finish")


def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def parse_stats(text: str):
    values = {}
    for item in text.split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            values[key] = int(value)
    return values


def averages(rows):
    return {
        metric: sum(float(row[metric]) for row in rows.values()) / len(rows)
        for metric in METRICS
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--v81", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()

    v6, v81 = read(args.v6), read(args.v81)
    if set(v6) != set(v81):
        raise ValueError("V6 and V8.1 case sets differ")

    old, new = averages(v6), averages(v81)
    composite = 100.0 * sum(new[m] / old[m] - 1.0 for m in METRICS) / 3.0
    strict = Counter()
    totals = Counter()
    accepted_cases = []
    case_rows = []
    for case in sorted(v81):
        baseline, candidate = v6[case], v81[case]
        deltas = [float(candidate[m]) - float(baseline[m]) for m in METRICS]
        if all(value <= 0 for value in deltas) and any(value < 0 for value in deltas):
            outcome = "improved"
        elif all(value >= 0 for value in deltas) and any(value > 0 for value in deltas):
            outcome = "regressed"
        elif all(value == 0 for value in deltas):
            outcome = "equal"
        else:
            outcome = "mixed"
        strict[outcome] += 1
        stats = parse_stats(candidate.get("emergency_stats", ""))
        totals.update(stats)
        if stats.get("accepted", 0):
            accepted_cases.append(case)
        case_rows.append([
            case, candidate["is_legal"], candidate["selected_config"],
            candidate["E_wait"], candidate["E_memory_new"], candidate["E_finish"],
            candidate["elapsed_sec"], outcome,
            stats.get("triggered", 0), stats.get("accepted", 0),
            stats.get("attempted", 0), stats.get("reject_wait", 0),
            stats.get("reject_memory", 0), stats.get("reject_finish", 0),
            stats.get("skipped_time", 0),
        ])

    legal = sum(row["is_legal"] in {"1", "True", "true"} for row in v81.values())
    max_runtime = max(float(row["elapsed_sec"]) for row in v81.values())
    case100 = float(v81["case100.in"]["elapsed_sec"])
    verified = (
        legal == 100
        and max_runtime < 60.0
        and strict["regressed"] <= 1
        and composite < 0.0
    )
    lines = [
        "# V8.1 Emergency Skeleton Summary", "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| V6 safe | 100/100 | {old['E_wait']:.2f} | {old['E_memory_new']:.2f} | {old['E_finish']:.2f} | {max(float(r['elapsed_sec']) for r in v6.values()):.6f} | {float(v6['case100.in']['elapsed_sec']):.6f} |",
        f"| V8.1 guarded | {legal}/100 | {new['E_wait']:.2f} | {new['E_memory_new']:.2f} | {new['E_finish']:.2f} | {max_runtime:.6f} | {case100:.6f} |",
        "",
        f"Composite change vs V6: {composite:+.6f}%.",
        f"Strict improved/regressed/mixed/equal: {strict['improved']}/{strict['regressed']}/{strict['mixed']}/{strict['equal']}.",
        f"Detector triggers: {totals['triggered']}.",
        f"Accepted: {totals['accepted']}.",
        f"Rejected by wait/memory/finish guard: {totals['reject_wait']}/{totals['reject_memory']}/{totals['reject_finish']}.",
        f"Skipped due to time: {totals['skipped_time']}.",
        f"Accepted cases: {', '.join(accepted_cases) if accepted_cases else 'none'}.",
        f"Verification verdict: {'PASS' if verified else 'FAIL'}; default remains V6 safe.",
        "",
        "## Control Cases", "",
    ]
    for case in ("case036.in", "case035.in", "case038.in", "case080.in"):
        row = v81[case]
        stats = parse_stats(row["emergency_stats"])
        lines.append(
            f"- {case}: selected={row['selected_config']}, triggered={stats.get('triggered', 0)}, "
            f"accepted={stats.get('accepted', 0)}, E_wait={float(row['E_wait']):.0f}, "
            f"E_memory_new={float(row['E_memory_new']):.0f}, E_finish={float(row['E_finish']):.0f}."
        )
    lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    args.cases.parent.mkdir(parents=True, exist_ok=True)
    with args.cases.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow([
            "case", "is_legal", "selected_candidate", "E_wait", "E_memory_new",
            "E_finish", "runtime_sec", "outcome_vs_v6", "detector_triggered",
            "accepted", "attempted", "rejected_wait", "rejected_memory",
            "rejected_finish", "skipped_due_to_time",
        ])
        writer.writerows(case_rows)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
