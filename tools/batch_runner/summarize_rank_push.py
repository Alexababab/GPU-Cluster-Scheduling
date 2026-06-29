#!/usr/bin/env python3
"""Summarize rank-push batch CSVs and portfolio selections."""

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
    elapsed_sec: float
    e_wait: float
    e_memory_old: float
    e_memory_new: float
    e_finish: float
    selected_config: str


def parse_version(value: str) -> tuple[str, Path]:
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
                legal=row["is_legal"].strip() in {"1", "true", "True"},
                elapsed_sec=float(row["elapsed_sec"]),
                e_wait=float(row["E_wait"]),
                e_memory_old=float(row["E_memory_old"]),
                e_memory_new=float(row["E_memory_new"]),
                e_finish=float(row["E_finish"]),
                selected_config=row.get("selected_config", "").strip(),
            )
    return cases


def average(cases: list[CaseMetrics], field: str) -> float:
    return sum(getattr(case, field) for case in cases) / len(cases)


def strict_counts(
    baseline: dict[str, CaseMetrics],
    portfolio: dict[str, CaseMetrics],
) -> tuple[int, int, int]:
    improved = worsened = mixed = 0
    for case_name in sorted(set(baseline) & set(portfolio)):
        old = baseline[case_name]
        new = portfolio[case_name]
        deltas = (
            new.e_wait - old.e_wait,
            new.e_memory_new - old.e_memory_new,
            new.e_finish - old.e_finish,
        )
        if all(delta <= 0 for delta in deltas) and any(
            delta < 0 for delta in deltas
        ):
            improved += 1
        elif all(delta >= 0 for delta in deltas) and any(
            delta > 0 for delta in deltas
        ):
            worsened += 1
        else:
            mixed += 1
    return improved, worsened, mixed


def build_report(versions: dict[str, dict[str, CaseMetrics]]) -> str:
    lines = [
        "# Rank Push Portfolio Summary",
        "",
        "| version | legal | avg E_wait | avg E_memory_old | "
        "avg E_memory_new | avg E_finish | max runtime (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, case_map in versions.items():
        legal = [case for case in case_map.values() if case.legal]
        lines.append(
            f"| {name} | {len(legal)}/{len(case_map)} | "
            f"{average(legal, 'e_wait'):.2f} | "
            f"{average(legal, 'e_memory_old'):.5f} | "
            f"{average(legal, 'e_memory_new'):.2f} | "
            f"{average(legal, 'e_finish'):.2f} | "
            f"{max(case.elapsed_sec for case in case_map.values()):.6f} |"
        )

    portfolio = versions["portfolio"]
    lines.extend(["", "## Portfolio Comparisons", ""])
    for name in ("v1b", "v1c", "v1d"):
        improved, worsened, mixed = strict_counts(versions[name], portfolio)
        lines.append(
            f"- vs {name}: strict improved {improved}, "
            f"strict worsened {worsened}, mixed/tied {mixed}."
        )

    selections = Counter(
        case.selected_config for case in portfolio.values()
    )
    lines.extend(["", "## Selection Distribution", ""])
    for config, count in selections.most_common():
        lines.append(f"- {config}: {count}")
    lines.append("")
    return "\n".join(lines)


def write_selections(
    path: Path,
    versions: dict[str, dict[str, CaseMetrics]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    portfolio = versions["portfolio"]
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "case",
                "selected_config",
                "E_wait",
                "E_memory_old",
                "E_memory_new",
                "E_finish",
                "runtime_sec",
            ]
        )
        for case_name in sorted(portfolio):
            case = portfolio[case_name]
            writer.writerow(
                [
                    case.case,
                    case.selected_config,
                    case.e_wait,
                    case.e_memory_old,
                    case.e_memory_new,
                    case.e_finish,
                    case.elapsed_sec,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("versions", nargs="+", type=parse_version)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selections", type=Path, required=True)
    args = parser.parse_args()

    versions = {
        name: read_cases(path)
        for name, path in args.versions
    }
    required = {"v1b", "v1c", "v1d", "portfolio"}
    if set(versions) != required:
        parser.error(f"versions must be exactly: {sorted(required)}")

    report = build_report(versions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8", newline="\n")
    write_selections(args.selections, versions)
    print(report)
    print(f"Selections: {args.selections.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
