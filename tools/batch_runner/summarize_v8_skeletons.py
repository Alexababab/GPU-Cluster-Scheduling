#!/usr/bin/env python3
"""Compare V8 skeleton generators against the V6-safe baseline."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

COLUMNS = ("E_wait", "E_memory_new", "E_finish")


def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def average(rows):
    return {column: sum(float(row[column]) for row in rows.values()) / len(rows) for column in COLUMNS}


def strict(old, new):
    improved = regressed = mixed = 0
    for case in old:
        delta = [float(new[case][column]) - float(old[case][column]) for column in COLUMNS]
        if all(value <= 0 for value in delta) and any(value < 0 for value in delta): improved += 1
        elif all(value >= 0 for value in delta) and any(value > 0 for value in delta): regressed += 1
        else: mixed += 1
    return improved, regressed, mixed


def relative_score(row, baseline):
    def relative(column):
        old = float(baseline[column])
        new = float(row[column])
        if old == 0.0:
            return 0.0 if new == 0.0 else new
        return new / old - 1.0
    return relative("E_wait") + 1.25 * relative("E_memory_new") + relative("E_finish")


def parse_stats(text):
    result = {}
    for item in text.split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            result[key] = value
    return result


def source(name):
    if name.startswith("hard_"): return "hard_job_skeleton"
    if name.startswith("reservation_"): return "reservation_profile"
    if name.startswith("regret"): return "regret_constructor"
    return "window_repacking"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    baseline = read(args.baseline)
    names = [
        "hard_p5_slack0", "hard_p10_slack0", "hard_p15_slack0",
        "hard_p10_slack_light", "hard_p15_slack_light",
        "reservation_top3_strict", "reservation_top5_slack",
        "reservation_top10_slack", "regret2_all", "regret3_all",
        "regret2_hard_first", "window_memory_hotspot",
        "window_wait_hotspot", "window_tail_hotspot",
    ]
    results = {}
    for name in names:
        prefix = "v8-fixed-" if name.startswith("window_") else "v8-"
        results[name] = read(args.root / f"{prefix}{name}" / "batch_summary.csv")
    base_avg = average(baseline)
    selected = Counter()
    winner_profiles = defaultdict(Counter)
    loser_profiles = defaultdict(Counter)
    case_rows = []
    for case in baseline:
        choices = {name: relative_score(rows[case], baseline[case]) for name, rows in results.items()}
        best_name, best_score = min(choices.items(), key=lambda item: item[1])
        if best_score >= 0:
            best_name = "v6_safe"
        selected[best_name] += 1
        if best_name != "v6_safe":
            winner_profiles[source(best_name)][baseline[case].get("profile", "unknown")] += 1
        for name, score in choices.items():
            if score > 0.03:
                loser_profiles[source(name)][baseline[case].get("profile", "unknown")] += 1
        row = baseline[case] if best_name == "v6_safe" else results[best_name][case]
        stats = parse_stats(row.get("v7_stats", ""))
        task_count = int(baseline[case].get("task_count", 0))
        hard_count = 0
        protected_count = 0
        window_size = 0
        if best_name.startswith("hard_p"):
            percent = 15 if "p15" in best_name else (10 if "p10" in best_name else 5)
            hard_count = max(1, task_count * percent // 100)
        elif best_name.startswith("reservation_top"):
            protected_count = 10 if "top10" in best_name else (5 if "top5" in best_name else 3)
        elif best_name.startswith("window_"):
            limit = 120 if task_count < 500 else (80 if task_count < 2500 else 50)
            window_size = min(limit, max(5, task_count // 10))
        case_rows.append([
            case, baseline[case]["E_wait"], baseline[case]["E_memory_new"],
            baseline[case]["E_finish"], best_name, row["E_wait"],
            row["E_memory_new"], row["E_finish"],
            float(row["E_wait"]) - float(baseline[case]["E_wait"]),
            float(row["E_memory_new"]) - float(baseline[case]["E_memory_new"]),
            float(row["E_finish"]) - float(baseline[case]["E_finish"]),
            row["elapsed_sec"], baseline[case].get("profile", ""), hard_count,
            protected_count, window_size,
            "v6_safe" if best_name == "v6_safe" else source(best_name),
        ])

    lines = [
        "# V8 Skeleton Benchmark", "",
        "| candidate | source | legal | selected | avg E_wait | avg E_memory_new | avg E_finish | composite vs V6 | strict I/R/M | max runtime | case100 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    promising = []
    for name in names:
        rows = results[name]
        avg = average(rows)
        composite = 100 * sum(avg[column] / base_avg[column] - 1 for column in COLUMNS) / 3
        counts = strict(baseline, rows)
        legal = sum(row["is_legal"] in {"1", "true", "True"} for row in rows.values())
        if legal == 100 and counts[0] >= 15 and counts[1] <= 5 and composite <= -0.05:
            promising.append(name)
        lines.append(
            f"| {name} | {source(name)} | {legal}/100 | {selected[name]} | "
            f"{avg['E_wait']:.2f} | {avg['E_memory_new']:.2f} | {avg['E_finish']:.2f} | "
            f"{composite:+.6f}% | {counts[0]}/{counts[1]}/{counts[2]} | "
            f"{max(float(row['elapsed_sec']) for row in rows.values()):.6f} | "
            f"{float(rows['case100.in']['elapsed_sec']):.6f} |"
        )
        best_cases = sorted(
            ((relative_score(rows[case], baseline[case]), case) for case in baseline),
            key=lambda item: item[0]
        )[:3]
        lines.append(
            f"<!-- best {name}: " + ", ".join(
                f"{case} ({score * 100:+.4f}%)" for score, case in best_cases
            ) + " -->"
        )
    oracle_metrics = {column: 0.0 for column in COLUMNS}
    for row in case_rows:
        oracle_metrics["E_wait"] += float(row[5]) / len(case_rows)
        oracle_metrics["E_memory_new"] += float(row[6]) / len(case_rows)
        oracle_metrics["E_finish"] += float(row[7]) / len(case_rows)
    oracle_composite = 100 * sum(
        oracle_metrics[column] / base_avg[column] - 1 for column in COLUMNS
    ) / 3
    lines += [
        "", "Promising skeletons: " + (", ".join(promising) if promising else "none") + ".",
        f"Combined per-case skeleton oracle composite vs V6: {oracle_composite:+.6f}%.",
        "", "## Oracle Selection Counts", "",
    ]
    for name, count in selected.most_common(): lines.append(f"- {name}: {count}")
    lines += ["", "## Winner Profiles", ""]
    for family, counts in winner_profiles.items(): lines.append(f"- {family}: {dict(counts)}")
    lines += ["", "## Loser Profiles", ""]
    for family, counts in loser_profiles.items(): lines.append(f"- {family}: {dict(counts)}")
    lines.append("")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    with args.cases.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["case","V6_E_wait","V6_E_memory_new","V6_E_finish","selected_skeleton","selected_E_wait","selected_E_memory_new","selected_E_finish","E_wait_delta","E_memory_delta","E_finish_delta","runtime","case_profile","hard_job_count","protected_job_count","window_size","candidate_source"])
        writer.writerows(case_rows)
    print("\n".join(lines))


if __name__ == "__main__": main()
