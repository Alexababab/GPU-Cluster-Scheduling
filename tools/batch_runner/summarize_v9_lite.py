#!/usr/bin/env python3
"""Summarize V9-lite pathology-router experiments."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


METRICS = ("E_wait", "E_memory_new", "E_finish")
SOLVERS = ("tail", "memory", "shape", "blocker")


def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def stats(text: str):
    result = {}
    for item in text.split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            result[key] = int(value)
    return result


def averages(rows):
    return {m: sum(float(row[m]) for row in rows.values()) / len(rows) for m in METRICS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--v9", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    v6, v9 = read(args.v6), read(args.v9)
    if set(v6) != set(v9):
        raise ValueError("case sets differ")

    old, new = averages(v6), averages(v9)
    composite = 100 * sum(new[m] / old[m] - 1 for m in METRICS) / 3
    outcomes = Counter()
    totals = Counter()
    accepted_cases = defaultdict(list)
    solver_deltas = defaultdict(lambda: defaultdict(list))
    case_rows = []
    for case in sorted(v9):
        base, row = v6[case], v9[case]
        delta = {m: float(row[m]) - float(base[m]) for m in METRICS}
        values = list(delta.values())
        if all(v <= 0 for v in values) and any(v < 0 for v in values):
            outcome = "improved"
        elif all(v >= 0 for v in values) and any(v > 0 for v in values):
            outcome = "regressed"
        elif all(v == 0 for v in values):
            outcome = "equal"
        else:
            outcome = "mixed"
        outcomes[outcome] += 1
        parsed = stats(row.get("pathology_stats", ""))
        totals.update(parsed)
        selected = row["selected_config"]
        for solver in SOLVERS:
            if parsed.get(f"accept_{solver}", 0):
                accepted_cases[solver].append(case)
                for metric in METRICS:
                    solver_deltas[solver][metric].append(delta[metric])
                solver_deltas[solver]["proxy_gain"].append(-sum(
                    delta[metric] / max(1.0, float(base[metric])) *
                    (1.25 if metric == "E_memory_new" else 1.0)
                    for metric in METRICS
                ))
                solver_deltas[solver]["runtime"].append(
                    float(row["elapsed_sec"]) - float(base["elapsed_sec"])
                )
        case_rows.append([
            case, row["is_legal"], selected, row["E_wait"], row["E_memory_new"],
            row["E_finish"], row["elapsed_sec"], outcome,
            *(parsed.get(f"trigger_{s}", 0) for s in SOLVERS),
            *(parsed.get(f"run_{s}", 0) for s in SOLVERS),
            *(parsed.get(f"accept_{s}", 0) for s in SOLVERS),
        ])

    legal = sum(row["is_legal"] in {"1", "true", "True"} for row in v9.values())
    max_runtime = max(float(row["elapsed_sec"]) for row in v9.values())
    case100 = float(v9["case100.in"]["elapsed_sec"])
    accepted_total = sum(totals[f"accept_{s}"] for s in SOLVERS)
    verified = legal == 100 and max_runtime < 60 and case100 < 60 and composite < -0.03 and outcomes["regressed"] <= 2 and accepted_total >= 10 and (totals["accept_tail"] > 0 or totals["accept_memory"] > 0)
    lines = [
        "# V9-lite Pathology Router Summary", "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| V6 safe | 100/100 | {old['E_wait']:.2f} | {old['E_memory_new']:.2f} | {old['E_finish']:.2f} | {max(float(r['elapsed_sec']) for r in v6.values()):.6f} | {float(v6['case100.in']['elapsed_sec']):.6f} |",
        f"| V9 lite | {legal}/100 | {new['E_wait']:.2f} | {new['E_memory_new']:.2f} | {new['E_finish']:.2f} | {max_runtime:.6f} | {case100:.6f} |",
        "",
        f"Composite change vs V6: {composite:+.6f}%.",
        f"Strict improved/regressed/mixed/equal: {outcomes['improved']}/{outcomes['regressed']}/{outcomes['mixed']}/{outcomes['equal']}.",
        f"Accepted solver improvements: {accepted_total}.",
        f"Verification verdict: {'PASS' if verified else 'FAIL'}.",
        "", "## Router", "",
    ]
    for solver in SOLVERS:
        lines.append(
            f"- {solver}: trigger={totals[f'trigger_{solver}']}, run={totals[f'run_{solver}']}, "
            f"accept={totals[f'accept_{solver}']}, cases={','.join(accepted_cases[solver]) or 'none'}"
        )
    lines.extend([
        f"- rejected wait/memory/finish/proxy/illegal/timeout: {totals['reject_wait']}/{totals['reject_memory']}/{totals['reject_finish']}/{totals['reject_proxy']}/{totals['reject_illegal']}/{totals['reject_timeout']}",
        f"- skipped due to time: {totals['skipped_time']}",
        "", "## Accepted Solver Deltas", "",
        "| solver | cases | avg delta wait | avg delta memory | avg delta finish | avg runtime cost | proxy gain/sec |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for solver in SOLVERS:
        count = len(accepted_cases[solver])
        if not count:
            lines.append(f"| {solver} | 0 | 0 | 0 | 0 | 0 | 0 |")
            continue
        avg = lambda key: sum(solver_deltas[solver][key]) / count
        runtime = sum(max(0.0, value) for value in solver_deltas[solver]["runtime"])
        gain_per_second = sum(solver_deltas[solver]["proxy_gain"]) / max(1e-9, runtime)
        lines.append(f"| {solver} | {count} | {avg('E_wait'):.2f} | {avg('E_memory_new'):.2f} | {avg('E_finish'):.2f} | {avg('runtime'):.6f} | {gain_per_second:.6f} |")
    lines.extend(["", "## Controls", ""])
    for case in ("case036.in", "case035.in", "case038.in", "case080.in"):
        row = v9[case]
        parsed = stats(row["pathology_stats"])
        lines.append(f"- {case}: selected={row['selected_config']}, blocker_trigger={parsed.get('trigger_blocker', 0)}, blocker_accept={parsed.get('accept_blocker', 0)}.")
    lines.append("")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    with args.cases.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["case", "is_legal", "selected_solver", "E_wait", "E_memory_new", "E_finish", "runtime_sec", "outcome_vs_v6", *(f"trigger_{s}" for s in SOLVERS), *(f"run_{s}" for s in SOLVERS), *(f"accept_{s}" for s in SOLVERS)])
        writer.writerows(case_rows)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
