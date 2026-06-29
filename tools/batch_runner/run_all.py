#!/usr/bin/env python3
"""Run every .in case, validate each schedule, and export V0 metrics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RunResult:
    case_name: str
    exit_code: int = 0
    elapsed_sec: float = 0.0
    timed_out: bool = False
    output_lines: int = 0
    task_count: int = 0
    is_legal: bool | None = None
    e_wait: float | None = None
    e_memory: float | None = None
    e_finish: float | None = None
    error: str = ""

    @property
    def passed(self) -> bool:
        return (
            self.exit_code == 0
            and not self.timed_out
            and self.is_legal is True
        )


def read_task_count(input_path: Path) -> int:
    with input_path.open("r", encoding="utf-8") as source:
        fields = source.readline().split()
    return int(fields[1]) if len(fields) >= 2 else 0


def run_scheduler(
    input_path: Path,
    output_path: Path,
    scheduler_path: Path,
    timeout_sec: int,
    scheduler_config: str | None,
) -> RunResult:
    result = RunResult(
        case_name=input_path.name,
        task_count=read_task_count(input_path),
    )
    start = time.perf_counter()

    try:
        with input_path.open("r", encoding="utf-8") as source:
            with output_path.open("w", encoding="utf-8", newline="\n") as target:
                process = subprocess.run(
                    [str(scheduler_path)],
                    stdin=source,
                    stdout=target,
                    stderr=subprocess.PIPE,
                    timeout=timeout_sec,
                    text=True,
                    encoding="utf-8",
                    env={
                        **os.environ,
                        **(
                            {"SCHEDULER_CONFIG": scheduler_config}
                            if scheduler_config
                            else {}
                        ),
                    },
                )
        result.elapsed_sec = time.perf_counter() - start
        result.exit_code = process.returncode
        result.output_lines = sum(
            1
            for _ in output_path.open("r", encoding="utf-8")
        )
        if process.stderr.strip():
            result.error = process.stderr.strip()[:500]
    except subprocess.TimeoutExpired:
        result.elapsed_sec = time.perf_counter() - start
        result.exit_code = -1
        result.timed_out = True
        result.error = f"scheduler timeout ({timeout_sec}s)"
        output_path.unlink(missing_ok=True)
    except FileNotFoundError:
        result.exit_code = -2
        result.error = f"scheduler not found: {scheduler_path}"
    except Exception as error:
        result.exit_code = -3
        result.error = str(error)[:500]

    return result


def run_validator(
    result: RunResult,
    input_path: Path,
    output_path: Path,
    validator_path: Path,
    timeout_sec: int,
) -> None:
    if result.exit_code != 0 or result.timed_out:
        result.is_legal = False
        return

    try:
        validator_input = (
            input_path.read_text(encoding="utf-8").rstrip()
            + "\n"
            + output_path.read_text(encoding="utf-8")
        )
        process = subprocess.run(
            [str(validator_path), "--quiet"],
            input=validator_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            text=True,
            encoding="utf-8",
        )

        stdout = process.stdout.strip()
        if not stdout:
            result.is_legal = False
            result.error = (
                process.stderr.strip() or "validator produced no JSON"
            )[:500]
            return

        payload = json.loads(stdout)
        result.is_legal = bool(payload.get("valid", False))
        if not result.is_legal:
            result.error = (
                f"validator rejected schedule "
                f"({payload.get('errors', 'unknown')} errors)"
            )
            return

        if process.returncode != 0:
            result.is_legal = False
            result.error = (
                process.stderr.strip()
                or f"validator exited with {process.returncode}"
            )[:500]
            return

        result.e_wait = float(payload["E_wait"])
        result.e_memory = float(payload["E_memory"])
        result.e_finish = float(payload["E_finish"])
    except subprocess.TimeoutExpired:
        result.is_legal = False
        result.error = f"validator timeout ({timeout_sec}s)"
    except FileNotFoundError:
        result.is_legal = False
        result.error = f"validator not found: {validator_path}"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        result.is_legal = False
        result.error = f"invalid validator JSON: {error}"
    except Exception as error:
        result.is_legal = False
        result.error = str(error)[:500]


def write_metadata(path: Path, result: RunResult) -> None:
    fields = {
        "case": result.case_name,
        "exit_code": result.exit_code,
        "elapsed_sec": f"{result.elapsed_sec:.6f}",
        "timed_out": result.timed_out,
        "output_lines": result.output_lines,
        "task_count": result.task_count,
        "is_legal": result.is_legal,
        "E_wait": result.e_wait,
        "E_memory": result.e_memory,
        "E_finish": result.e_finish,
        "error": result.error,
    }
    text = "".join(f"{key}={value}\n" for key, value in fields.items())
    path.write_text(text, encoding="utf-8", newline="\n")


def export_csv(path: Path, results: list[RunResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "case",
                "exit_code",
                "elapsed_sec",
                "timed_out",
                "output_lines",
                "task_count",
                "is_legal",
                "E_wait",
                "E_memory",
                "E_finish",
                "error",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.case_name,
                    result.exit_code,
                    f"{result.elapsed_sec:.6f}",
                    int(result.timed_out),
                    result.output_lines,
                    result.task_count,
                    int(result.is_legal)
                    if result.is_legal is not None
                    else "",
                    result.e_wait if result.e_wait is not None else "",
                    result.e_memory if result.e_memory is not None else "",
                    result.e_finish if result.e_finish is not None else "",
                    result.error,
                ]
            )


def print_summary(results: list[RunResult]) -> None:
    passed = [result for result in results if result.passed]
    elapsed = [
        result.elapsed_sec
        for result in results
        if result.exit_code == 0 and not result.timed_out
    ]

    print("\n" + "=" * 60)
    print("Batch summary")
    print("=" * 60)
    print(f"cases:        {len(results)}")
    print(f"passed:       {len(passed)}/{len(results)}")
    print(f"illegal:      {sum(result.is_legal is False for result in results)}")
    print(f"timeouts:     {sum(result.timed_out for result in results)}")
    print(
        f"run errors:   "
        f"{sum(result.exit_code != 0 and not result.timed_out for result in results)}"
    )
    if elapsed:
        print(f"fastest:      {min(elapsed):.3f}s")
        print(f"slowest:      {max(elapsed):.3f}s")
        print(f"average:      {sum(elapsed) / len(elapsed):.3f}s")
        print(f"total:        {sum(elapsed):.3f}s")

    failed = [result for result in results if not result.passed]
    if failed:
        print("\nFailed cases:")
        for result in failed:
            print(f"- {result.case_name}: {result.error}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("instances_dir", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scheduler", type=Path, default=Path("build/scheduler"))
    parser.add_argument("--validator", type=Path, default=Path("build/validator"))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--scheduler-config")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instances_dir = args.instances_dir.resolve()
    scheduler_path = args.scheduler.resolve()
    validator_path = args.validator.resolve()

    if not instances_dir.is_dir():
        print(f"instances directory not found: {instances_dir}", file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (
            Path(__file__).resolve().parents[2]
            / "experiments"
            / "results"
            / f"run_{timestamp}"
        )
    )
    csv_path = (
        args.csv.resolve()
        if args.csv
        else output_dir / "batch_summary.csv"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = sorted(instances_dir.glob("*.in"))
    if not input_paths:
        print(f"no .in files found: {instances_dir}", file=sys.stderr)
        return 2

    print(f"instances: {instances_dir}")
    print(f"outputs:   {output_dir}")
    print(f"scheduler: {scheduler_path}")
    print(f"validator: {validator_path}")
    print(f"config:    {args.scheduler_config or '(inherited/default)'}")
    print(f"timeout:   {args.timeout}s")
    print("-" * 60)

    results: list[RunResult] = []
    for index, input_path in enumerate(input_paths, 1):
        output_path = output_dir / f"{input_path.stem}.out"
        result = run_scheduler(
            input_path,
            output_path,
            scheduler_path,
            args.timeout,
            args.scheduler_config,
        )
        run_validator(
            result,
            input_path,
            output_path,
            validator_path,
            args.timeout,
        )
        write_metadata(output_dir / f"{input_path.stem}.meta", result)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(
            f"[{index:>3}/{len(input_paths)}] {input_path.name:<16} "
            f"{status} ({result.elapsed_sec:.3f}s, "
            f"{result.output_lines} lines)"
        )

    export_csv(csv_path, results)
    print_summary(results)
    print(f"CSV: {csv_path}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
