#!/usr/bin/env python3
"""批量运行工具 —— 对所有 .in 文件运行调度程序并记录结果。

用法：
  python3 run_all.py <instances_dir> [options]

选项：
  --timeout SECONDS    每个实例的超时秒数（默认60）
  --output-dir DIR     输出目录（默认 experiments/results/<timestamp>/）
  --scheduler PATH     调度程序路径（默认 ./build/scheduler）
  --validator PATH     验证器路径（暂未实现，预留）
  --csv PATH           汇总 CSV 路径

输出：
  - experiments/results/<run_id>/caseXXX.out   每个实例的输出
  - experiments/results/<run_id>/caseXXX.meta  每个实例的元数据（时间、退出码）
  - experiments/summaries/batch_summary.csv    汇总表
"""

import csv
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 运行结果
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """单个实例的运行结果"""
    case_name: str
    exit_code: int = 0
    elapsed_sec: float = 0.0
    timed_out: bool = False
    error_msg: str = ""
    output_size: int = 0       # 输出行数

    # 三项原始指标（暂由外部工具填充）
    e_wait: Optional[float] = None
    e_memory: Optional[float] = None
    e_finish: Optional[float] = None

    # 合法性（暂由外部验证器填充）
    is_legal: Optional[bool] = None
    legality_errors: List[str] = field(default_factory=list)

    # 任务数统计
    task_count: int = 0


def run_one_instance(
    input_path: str,
    output_path: str,
    scheduler_path: str,
    timeout_sec: int = 60,
) -> RunResult:
    """运行单个实例并返回结果"""
    case_name = os.path.basename(input_path)
    result = RunResult(case_name=case_name)

    # 读取输入文件的任务数（用于合法性快速检查）
    try:
        with open(input_path, "r") as f:
            first_line = f.readline().strip()
            parts = first_line.split()
            if len(parts) >= 2:
                result.task_count = int(parts[1])
    except Exception:
        pass

    start = time.perf_counter()

    try:
        with open(input_path, "r") as fin, open(output_path, "w") as fout:
            proc = subprocess.run(
                [scheduler_path],
                stdin=fin,
                stdout=fout,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                text=True,
            )
        result.exit_code = proc.returncode
        result.elapsed_sec = time.perf_counter() - start

        # 读取输出行数
        if os.path.exists(output_path):
            with open(output_path, "r") as f:
                result.output_size = sum(1 for _ in f)

        # 捕获 stderr 中的错误信息
        if proc.stderr.strip():
            result.error_msg = proc.stderr.strip()[:500]

    except subprocess.TimeoutExpired:
        result.timed_out = True
        result.elapsed_sec = time.perf_counter() - start
        result.exit_code = -1
        result.error_msg = f"超时（>{timeout_sec}s）"
        # 删除不完整的输出文件
        if os.path.exists(output_path):
            os.remove(output_path)

    except FileNotFoundError:
        result.exit_code = -2
        result.error_msg = f"调度程序不存在: {scheduler_path}"

    except Exception as e:
        result.exit_code = -3
        result.error_msg = str(e)[:500]

    return result


def run_all(
    instances_dir: str,
    output_dir: str,
    scheduler_path: str,
    timeout_sec: int = 60,
    validator_path: Optional[str] = None,
) -> List[RunResult]:
    """批量运行全部实例"""
    os.makedirs(output_dir, exist_ok=True)

    # 收集所有 .in 文件
    in_files = sorted(
        os.path.join(instances_dir, f)
        for f in os.listdir(instances_dir)
        if f.endswith(".in")
    )

    if not in_files:
        print(f"[错误] 没有找到 .in 文件: {instances_dir}")
        return []

    total = len(in_files)
    results: List[RunResult] = []

    print(f"实例目录: {instances_dir}")
    print(f"输出目录: {output_dir}")
    print(f"调度程序: {scheduler_path}")
    print(f"超时限制: {timeout_sec}s")
    print(f"实例总数: {total}")
    print("-" * 60)

    for i, in_path in enumerate(in_files):
        case_name = os.path.basename(in_path)
        out_name = case_name.replace(".in", ".out")
        out_path = os.path.join(output_dir, out_name)

        print(f"[{i+1:>3}/{total}] {case_name:<16} ", end="", flush=True)

        result = run_one_instance(in_path, out_path, scheduler_path, timeout_sec)
        results.append(result)

        # 简短结果
        if result.timed_out:
            print(f"超时 ({result.elapsed_sec:.1f}s)")
        elif result.exit_code != 0:
            print(f"错误 (exit={result.exit_code}) {result.error_msg[:60]}")
        else:
            print(f"通过 ({result.elapsed_sec:.2f}s, {result.output_size} 行)")

        # 写元数据文件
        meta_path = os.path.join(output_dir, case_name.replace(".in", ".meta"))
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"case={case_name}\n")
            f.write(f"exit_code={result.exit_code}\n")
            f.write(f"elapsed_sec={result.elapsed_sec:.6f}\n")
            f.write(f"timed_out={result.timed_out}\n")
            f.write(f"output_lines={result.output_size}\n")
            f.write(f"task_count={result.task_count}\n")
            if result.error_msg:
                f.write(f"error={result.error_msg}\n")

    return results


def print_summary(results: List[RunResult]):
    """打印汇总信息"""
    total = len(results)
    success = sum(1 for r in results if r.exit_code == 0 and not r.timed_out)
    timed_out = sum(1 for r in results if r.timed_out)
    errors = sum(1 for r in results if r.exit_code != 0 and not r.timed_out)

    elapsed_list = [r.elapsed_sec for r in results if r.exit_code == 0 and not r.timed_out]

    print("\n" + "=" * 60)
    print("批量运行汇总")
    print("=" * 60)
    print(f"  总实例数:   {total}")
    print(f"  成功:       {success} ({success/total*100:.1f}%)" if total else "")
    print(f"  超时:       {timed_out}")
    print(f"  运行错误:   {errors}")

    if elapsed_list:
        print(f"  最快:       {min(elapsed_list):.3f}s")
        print(f"  最慢:       {max(elapsed_list):.3f}s")
        print(f"  平均:       {sum(elapsed_list)/len(elapsed_list):.3f}s")
        print(f"  总耗时:     {sum(elapsed_list):.2f}s")

    # 列出失败实例
    failed = [r for r in results if r.exit_code != 0 or r.timed_out]
    if failed:
        print(f"\n  失败/超时实例:")
        for r in failed:
            reason = "超时" if r.timed_out else f"exit={r.exit_code}"
            print(f"    - {r.case_name}: {reason} {r.error_msg[:80]}")

    print("=" * 60)


def export_summary_csv(results: List[RunResult], csv_path: str):
    """导出汇总 CSV"""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "实例", "退出码", "耗时(s)", "超时", "输出行数", "任务数",
            "E_wait", "E_memory", "E_finish", "合法", "错误信息",
        ])
        for r in results:
            writer.writerow([
                r.case_name, r.exit_code, f"{r.elapsed_sec:.4f}",
                int(r.timed_out), r.output_size, r.task_count,
                f"{r.e_wait:.4f}" if r.e_wait is not None else "",
                f"{r.e_memory:.4f}" if r.e_memory is not None else "",
                f"{r.e_finish:.4f}" if r.e_finish is not None else "",
                int(r.is_legal) if r.is_legal is not None else "",
                r.error_msg,
            ])
    print(f"\n汇总 CSV: {csv_path}")


def main():
    # 解析参数
    args = sys.argv[1:]
    instances_dir = None
    output_dir = None
    scheduler_path = "./build/scheduler"
    timeout_sec = 60
    validator_path = None
    csv_path = None

    i = 0
    while i < len(args):
        if args[i] == "--timeout" and i + 1 < len(args):
            timeout_sec = int(args[i + 1]); i += 2
        elif args[i] == "--output-dir" and i + 1 < len(args):
            output_dir = args[i + 1]; i += 2
        elif args[i] == "--scheduler" and i + 1 < len(args):
            scheduler_path = args[i + 1]; i += 2
        elif args[i] == "--validator" and i + 1 < len(args):
            validator_path = args[i + 1]; i += 2
        elif args[i] == "--csv" and i + 1 < len(args):
            csv_path = args[i + 1]; i += 2
        elif not instances_dir:
            instances_dir = args[i]; i += 1
        else:
            i += 1

    if not instances_dir:
        print(f"用法: {sys.argv[0]} <instances_dir> [--timeout 60] [--output-dir DIR] [--scheduler PATH]")
        print(f"示例: {sys.argv[0]} instances/ --timeout 60")
        sys.exit(1)

    if not os.path.isdir(instances_dir):
        print(f"错误: 实例目录不存在 —— {instances_dir}")
        sys.exit(1)

    # 生成输出目录
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "experiments", "results", f"run_{timestamp}"
        )

    # 将调度程序路径转为绝对路径
    if not os.path.isabs(scheduler_path):
        scheduler_path = os.path.abspath(scheduler_path)

    # 运行
    results = run_all(instances_dir, output_dir, scheduler_path, timeout_sec, validator_path)

    # 输出
    print_summary(results)

    # 导出
    if not csv_path:
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "experiments", "summaries", "batch_summary.csv"
        )
    export_summary_csv(results, csv_path)


if __name__ == "__main__":
    main()
