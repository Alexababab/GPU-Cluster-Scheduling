#!/usr/bin/env python3
"""Build the V2 baseline, V2.1, and V2.2 selector comparison report."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CaseMetrics:
    case: str
    legal: bool
    elapsed: float
    wait: float
    memory: float
    finish: float
    selected_config: str


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=CSV_PATH")
    name, path = value.split("=", 1)
    return name, Path(path)


def read_cases(path: Path) -> dict[str, CaseMetrics]:
    cases: dict[str, CaseMetrics] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            case = row["case"]
            cases[case] = CaseMetrics(
                case=case,
                legal=row["is_legal"].strip().lower() in {"1", "true"},
                elapsed=float(row["elapsed_sec"]),
                wait=float(row["E_wait"]),
                memory=float(row["E_memory_new"]),
                finish=float(row["E_finish"]),
                selected_config=row.get("selected_config", "").strip(),
            )
    return cases


def average(cases: list[CaseMetrics], field: str) -> float:
    return sum(getattr(case, field) for case in cases) / len(cases)


def aggregate(cases: dict[str, CaseMetrics]) -> dict[str, float]:
    legal = [case for case in cases.values() if case.legal]
    case100 = cases["case100.in"]
    return {
        "legal": float(len(legal)),
        "count": float(len(cases)),
        "wait": average(legal, "wait"),
        "memory": average(legal, "memory"),
        "finish": average(legal, "finish"),
        "max_runtime": max(case.elapsed for case in cases.values()),
        "case100_runtime": case100.elapsed,
    }


def compare(
    baseline: dict[str, CaseMetrics],
    candidate: dict[str, CaseMetrics],
) -> tuple[int, int, int]:
    improved = worsened = mixed_or_tied = 0
    for case_name in sorted(set(baseline) & set(candidate)):
        old = baseline[case_name]
        new = candidate[case_name]
        deltas = (
            new.wait - old.wait,
            new.memory - old.memory,
            new.finish - old.finish,
        )
        if all(delta <= 0.0 for delta in deltas) and any(
            delta < 0.0 for delta in deltas
        ):
            improved += 1
        elif all(delta >= 0.0 for delta in deltas) and any(
            delta > 0.0 for delta in deltas
        ):
            worsened += 1
        else:
            mixed_or_tied += 1
    return improved, worsened, mixed_or_tied


def composite_delta(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> float:
    return 100.0 * sum(
        candidate[field] / baseline[field] - 1.0
        for field in ("wait", "memory", "finish")
    ) / 3.0


def metric_row(
    name: str,
    stats: dict[str, float],
    baseline_stats: dict[str, float],
    strict: tuple[int, int, int],
) -> str:
    improved, worsened, mixed = strict
    return (
        f"| {name} | {int(stats['legal'])}/{int(stats['count'])} | "
        f"{stats['wait']:.2f} | {stats['memory']:.2f} | "
        f"{stats['finish']:.2f} | "
        f"{composite_delta(baseline_stats, stats):+.6f}% | "
        f"{improved} | {worsened} | {mixed} | "
        f"{stats['max_runtime']:.6f} | {stats['case100_runtime']:.6f} |"
    )


def write_selection_matrix(
    path: Path,
    selectors: dict[str, dict[str, CaseMetrics]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selector_names = list(selectors)
    case_names = sorted(next(iter(selectors.values())))
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["case", *selector_names])
        for case_name in case_names:
            writer.writerow(
                [
                    case_name,
                    *(
                        selectors[name][case_name].selected_config
                        for name in selector_names
                    ),
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--selector", action="append", type=parse_named_path,
                        required=True)
    parser.add_argument("--candidate", action="append", type=parse_named_path,
                        default=[])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selections", type=Path, required=True)
    parser.add_argument("--default-selector", required=True)
    parser.add_argument("--final-default", type=Path)
    args = parser.parse_args()

    baseline = read_cases(args.baseline)
    selectors = {
        name: read_cases(path)
        for name, path in args.selector
    }
    candidates = {
        name: read_cases(path)
        for name, path in args.candidate
    }
    baseline_stats = aggregate(baseline)

    lines = [
        "# V2.1 and V2.2 Portfolio Tuning Summary",
        "",
        "## Baseline and Selector Results",
        "",
        "Composite delta is the mean percentage change of average E_wait, "
        "E_memory_new, and E_finish relative to V2; lower is better.",
        "",
        "| version / selector | legal | avg E_wait | avg E_memory_new | "
        "avg E_finish | composite vs V2 | strict improved | "
        "strict regressed | mixed/tied | max runtime (s) | case100 (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        metric_row(
            "V2 baseline",
            baseline_stats,
            baseline_stats,
            (0, 0, len(baseline)),
        ),
    ]

    for name, cases in selectors.items():
        lines.append(
            metric_row(
                name,
                aggregate(cases),
                baseline_stats,
                compare(baseline, cases),
            )
        )

    lines.extend(["", "## New Candidate Validation", ""])
    for name, cases in candidates.items():
        legal = sum(case.legal for case in cases.values())
        lines.append(f"- {name}: {legal}/{len(cases)} legal")

    lines.extend(
        [
            "",
            "## Default Selection",
            "",
            f"Default selector: `{args.default_selector}`.",
            "",
            "The environment variable `SCHEDULER_PORTFOLIO_SELECTOR` "
            "continues to override this default.",
        ]
    )
    if args.final_default:
        final_default = aggregate(read_cases(args.final_default))
        lines.extend(
            [
                "",
                (
                    "Final default-path verification: "
                    f"{int(final_default['legal'])}/{int(final_default['count'])} "
                    "legal, "
                    f"max runtime {final_default['max_runtime']:.6f}s, "
                    f"case100 {final_default['case100_runtime']:.6f}s."
                ),
            ]
        )

    lines.extend(["", "## Selector Choice Distribution", ""])
    for name, cases in selectors.items():
        counts = Counter(case.selected_config for case in cases.values())
        distribution = ", ".join(
            f"{config}={count}"
            for config, count in counts.most_common()
        )
        lines.append(f"- {name}: {distribution}")
    lines.append("")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    write_selection_matrix(args.selections, selectors)
    print("\n".join(lines))
    print(f"Selections: {args.selections.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
