#!/usr/bin/env python3
"""Summarize the V7 plan-repair experiment against V6 safe-anytime."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def parse_stats(text: str):
    result = {}
    for item in text.split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--v7", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    v6, v7 = read(args.v6), read(args.v7)
    columns = ("E_wait", "E_memory_new", "E_finish")
    old = {column: sum(float(row[column]) for row in v6.values()) / len(v6) for column in columns}
    new = {column: sum(float(row[column]) for row in v7.values()) / len(v7) for column in columns}
    composite = 100 * sum(new[column] / old[column] - 1 for column in columns) / 3
    improved = regressed = mixed = 0
    accepted = rejected = destroy_total = beam_total = 0
    operator_selected = [0] * 6
    operator_success = [0] * 6
    sources = Counter()
    case_rows = []
    for case, row in sorted(v7.items()):
        deltas = [float(row[column]) - float(v6[case][column]) for column in columns]
        if all(value <= 0 for value in deltas) and any(value < 0 for value in deltas): improved += 1
        elif all(value >= 0 for value in deltas) and any(value > 0 for value in deltas): regressed += 1
        else: mixed += 1
        stats = parse_stats(row.get("v7_stats", ""))
        accepted += int(stats.get("accepted", 0)); rejected += int(stats.get("rejected", 0))
        destroy_total += int(stats.get("destroy_total", 0)); beam_total += int(stats.get("beam", 0))
        selected = [int(value) for value in stats.get("selected", "0,0,0,0,0,0").split(",")]
        success = [int(value) for value in stats.get("success", "0,0,0,0,0,0").split(",")]
        operator_selected = [a + b for a, b in zip(operator_selected, selected)]
        operator_success = [a + b for a, b in zip(operator_success, success)]
        sources[row["selected_config"]] += 1
        case_rows.append([case, row["selected_config"], row["elapsed_sec"], stats.get("accepted", 0), row["E_wait"], row["E_memory_new"], row["E_finish"], sum(deltas), int(stats.get("destroy_total", 0)), stats.get("beam", 0), row["guard_triggered"]])
    lines = [
        "# V7 Plan Repair Summary", "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| V6 safe | 100/100 | {old['E_wait']:.2f} | {old['E_memory_new']:.2f} | {old['E_finish']:.2f} | {max(float(r['elapsed_sec']) for r in v6.values()):.6f} | {float(v6['case100.in']['elapsed_sec']):.6f} |",
        f"| V7 | {sum(r['is_legal'] in {'1','true','True'} for r in v7.values())}/100 | {new['E_wait']:.2f} | {new['E_memory_new']:.2f} | {new['E_finish']:.2f} | {max(float(r['elapsed_sec']) for r in v7.values()):.6f} | {float(v7['case100.in']['elapsed_sec']):.6f} |",
        "", f"Composite change vs V6: {composite:+.6f}%.",
        f"Strict improved/regressed/mixed: {improved}/{regressed}/{mixed}.",
        f"Accepted/rejected repairs: {accepted}/{rejected}.",
        f"Average destroy set size per attempted repair: {destroy_total / max(1, accepted + rejected):.2f}.",
        f"Average beam width: {beam_total / len(v7):.2f}.",
        f"Guard-triggered cases: {sum(r['guard_triggered'] == '1' for r in v7.values())}.",
        f"Operator selections: {operator_selected}.",
        f"Operator successes: {operator_success}.",
        "", "Result: V7 did not meet replacement thresholds; default remains V6 safe-anytime.", "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    with args.cases.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target); writer.writerow(["case","selected_final_source","runtime","accepted_repairs","E_wait","E_memory_new","E_finish","raw_metric_delta_sum","destroy_set_size_total","beam_width","guard_triggered"]); writer.writerows(case_rows)
    print("\n".join(lines))


if __name__ == "__main__": main()
