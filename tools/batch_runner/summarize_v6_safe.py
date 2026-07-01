#!/usr/bin/env python3
"""Summarize V6 safe-anytime and estimate per-case selector oracle gaps."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

FIELDS = ("wait", "memory", "finish")


def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def parse_candidates(text: str):
    result = {}
    for item in text.split(";"):
        if item:
            name, wait, memory, finish = item.split(":")
            result[name] = {"wait": float(wait), "memory": float(memory), "finish": float(finish)}
    return result


def norms(candidates):
    result = {name: {} for name in candidates}
    for field in FIELDS:
        values = [item[field] for item in candidates.values()]
        low, high = min(values), max(values)
        for name, item in candidates.items():
            result[name][field] = 0 if high <= low else (item[field] - low) / (high - low)
    return result


def scores(candidates, reference):
    normalized = norms(candidates)
    count = max(1, len(candidates) - 1)
    output = {}
    for name, item in candidates.items():
        minmax = normalized[name]["wait"] + 1.25 * normalized[name]["memory"] + normalized[name]["finish"]
        rank = sum(candidates[other][field] < item[field] for other in candidates for field in FIELDS) / count
        penalty = 0.35 if item["wait"] > reference["wait"] * 1.010 else 0
        penalty += 0.25 if item["finish"] > reference["finish"] * 1.006 else 0
        penalty += 0.20 if item["memory"] > reference["memory"] * 1.003 else 0
        output[name] = {"minmax": minmax, "rank": rank, "proxy": .45 * minmax + .55 * rank + penalty}
    return output


def aggregate(rows):
    values = list(rows.values())
    return {field: sum(float(row[{"wait":"E_wait","memory":"E_memory_new","finish":"E_finish"}[field]]) for row in values) / len(values) for field in FIELDS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    v5, v6 = read(args.v5), read(args.v6)
    old, new = aggregate(v5), aggregate(v6)
    composite = 100 * sum(new[field] / old[field] - 1 for field in FIELDS) / 3
    improved = regressed = mixed = 0
    for case in v6:
        deltas = [float(v6[case][column]) - float(v5[case][column]) for column in ("E_wait", "E_memory_new", "E_finish")]
        if all(value <= 0 for value in deltas) and any(value < 0 for value in deltas): improved += 1
        elif all(value >= 0 for value in deltas) and any(value > 0 for value in deltas): regressed += 1
        else: mixed += 1
    selected_counts = Counter(row["selected_config"] for row in v6.values())
    oracle_rows = []
    gaps = []
    for case, row in sorted(v6.items()):
        candidates = parse_candidates(row["candidate_metrics"])
        reference_name = "v5_heavy" if "v5_heavy" in candidates else next(iter(candidates))
        candidate_scores = scores(candidates, candidates[reference_name])
        proxy_best = min(candidate_scores, key=lambda name: candidate_scores[name]["proxy"])
        minmax_best = min(candidate_scores, key=lambda name: candidate_scores[name]["minmax"])
        rank_best = min(candidate_scores, key=lambda name: candidate_scores[name]["rank"])
        selected = row["selected_config"]
        gap = candidate_scores[selected]["proxy"] - candidate_scores[proxy_best]["proxy"]
        gaps.append(gap)
        oracle_rows.append([case, row["profile"], selected, row["E_wait"], row["E_memory_new"], row["E_finish"], row["elapsed_sec"], row["cheap_candidate_count"], row["repair_candidate_count"], row["guard_triggered"], proxy_best, minmax_best, rank_best, gap])
    lines = [
        "# V6 Safe-anytime Summary", "",
        "| version | legal | avg E_wait | avg E_memory_new | avg E_finish | max runtime | case100 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| V5 | 100/100 | {old['wait']:.2f} | {old['memory']:.2f} | {old['finish']:.2f} | {max(float(r['elapsed_sec']) for r in v5.values()):.6f} | {float(v5['case100.in']['elapsed_sec']):.6f} |",
        f"| V6 safe-anytime | {sum(r['is_legal'] in {'1','True','true'} for r in v6.values())}/100 | {new['wait']:.2f} | {new['memory']:.2f} | {new['finish']:.2f} | {max(float(r['elapsed_sec']) for r in v6.values()):.6f} | {float(v6['case100.in']['elapsed_sec']):.6f} |",
        "", f"Composite change vs V5: {composite:+.6f}%.",
        f"Strict improved/regressed/mixed: {improved}/{regressed}/{mixed}.",
        f"Average cheap candidates: {sum(int(r['cheap_candidate_count']) for r in v6.values()) / 100:.2f}.",
        f"Average repair candidates: {sum(int(r['repair_candidate_count']) for r in v6.values()) / 100:.2f}.",
        f"Guard-triggered cases: {sum(r['guard_triggered'] == '1' for r in v6.values())}.",
        f"Average leaderboard-proxy selector gap: {sum(gaps)/len(gaps):.9f}.",
        "", "## Selected Candidates", "",
    ]
    for name, count in selected_counts.most_common(): lines.append(f"- {name}: {count}")
    lines.append("")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    with args.cases.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target); writer.writerow(["case","profile","selected_candidate","E_wait","E_memory_new","E_finish","runtime","cheap_candidate_count","repair_candidate_count","guard_triggered","oracle_best_leaderboard_proxy","oracle_best_minmax","oracle_best_rank","selector_gap"]); writer.writerows(oracle_rows)
    print("\n".join(lines))


if __name__ == "__main__": main()
