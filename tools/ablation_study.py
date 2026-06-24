#!/usr/bin/env python3
"""消融实验工具 —— 自动生成对照组、运行对比、输出分析报告。

实验类型：
    task_ablation    任务评分组件消融（逐个关闭权重，衡量贡献）
    server_ablation  服务器评分组件消融（逐个关闭权重，衡量贡献）
    version_compare  V0 vs V1a vs V1b 三阶段对比
    scarcity_sweep   稀缺保护强度扫描（w_scarcity 多档对比）
    full             全部实验

用法：
    python3 tools/ablation_study.py instances/ --experiment task_ablation --quick
    python3 tools/ablation_study.py instances/ --experiment all
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 项目根目录
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEDULER = PROJECT_ROOT / "build" / "scheduler"
DEFAULT_VALIDATOR = PROJECT_ROOT / "build" / "validator"
DEFAULT_INSTANCES = PROJECT_ROOT / "instances"

QUICK_INSTANCES: list[str] = [
    "case001", "case002", "case003", "case004",
    "case011", "case012", "case013",
    "case021", "case051", "case081",
    "case091", "case095", "case098", "case100",
]


# ---------------------------------------------------------------------------
# 实验定义
# ---------------------------------------------------------------------------
# 默认权重（v1b 基线）
DEFAULT_PARAMS = {
    "task_scoring_enabled": "true",
    "w_priority": "2.0",
    "w_wait": "0.01",
    "w_scarcity": "40.0",
    "w_area": "0.20",
    "w_short_job": "4.0",
    "server_mode": "weighted",
    "w_gpu_fragment": "4.0",
    "w_gpu_memory_fragment": "2.0",
    "w_cpu_fragment": "1.0",
    "w_memory_fragment": "1.0",
}


@dataclass
class ExperimentVariant:
    """一个实验变体：名称 + 参数覆盖。"""
    name: str                      # 短名称，如 "no_scarcity"
    label: str                     # 显示标签，如 "关闭稀缺权重"
    description: str = ""          # 说明
    overrides: dict[str, str] = field(default_factory=dict)
    use_preset: str = ""           # 使用内置预设（v0/v1a/v1b），不写配置文件


def make_task_ablation() -> list[ExperimentVariant]:
    """任务评分组件消融。

    基线：v1b 默认权重。
    变体：逐个将任务评分权重置零，观察 E_wait 变化。
    """
    task_weights = [
        ("w_priority", "关闭优先级权重"),
        ("w_wait", "关闭等待时间权重"),
        ("w_scarcity", "关闭稀缺度权重"),
        ("w_area", "关闭 GPU-time 面积权重"),
        ("w_short_job", "关闭短作业偏好权重"),
    ]
    variants = [
        ExperimentVariant(
            name="baseline_v1b",
            label="基线（全部开启）",
            description="V1b 默认权重，所有评分组件生效",
        ),
    ]
    for key, label in task_weights:
        overrides = {key: "0.0"}
        variants.append(
            ExperimentVariant(
                name=f"no_{key}",
                label=label,
                description=f"将 {key} 设为 0，其他保持默认",
                overrides=overrides,
            )
        )
    # 全部关闭
    variants.append(
        ExperimentVariant(
            name="task_scoring_off",
            label="关闭全部任务排序",
            description="task_scoring_enabled = false，等价于 v1a 但保留加权服务器评分",
            overrides={"task_scoring_enabled": "false"},
        )
    )
    return variants


def make_server_ablation() -> list[ExperimentVariant]:
    """服务器评分组件消融。

    基线：v1b 默认权重。
    变体：逐个将服务器评分权重置零，观察 E_memory 变化。
    """
    server_weights = [
        ("w_gpu_fragment", "关闭 GPU 碎片惩罚"),
        ("w_gpu_memory_fragment", "关闭显存碎片惩罚"),
        ("w_cpu_fragment", "关闭 CPU 剩余率惩罚"),
        ("w_memory_fragment", "关闭内存剩余率惩罚"),
    ]
    variants = [
        ExperimentVariant(
            name="baseline_v1b",
            label="基线（全部开启）",
            description="V1b 默认权重，所有评分组件生效",
        ),
    ]
    for key, label in server_weights:
        overrides = {key: "0.0"}
        variants.append(
            ExperimentVariant(
                name=f"no_{key}",
                label=label,
                description=f"将 {key} 设为 0，其他保持默认",
                overrides=overrides,
            )
        )
    # 全部关闭 → 退化为 V0BestFit
    variants.append(
        ExperimentVariant(
            name="best_fit_mode",
            label="关闭全部服务器评分（Best Fit）",
            description="server_mode = best_fit，服务器选择退化为 V0 逻辑",
            overrides={"server_mode": "best_fit"},
        )
    )
    return variants


def make_version_compare() -> list[ExperimentVariant]:
    """V0 → V1a → V1b 三阶段对比。"""
    return [
        ExperimentVariant(
            name="v0_baseline",
            label="V0 基线",
            description="无任务排序 + Best Fit 服务器选择",
            use_preset="v0",
        ),
        ExperimentVariant(
            name="v1a_ordering",
            label="V1a 任务排序",
            description="启用任务评分排序 + Best Fit 服务器选择",
            use_preset="v1a",
        ),
        ExperimentVariant(
            name="v1b_full",
            label="V1b 完整评分",
            description="任务评分排序 + 加权服务器评分",
            use_preset="v1b",
        ),
    ]


def make_scarcity_sweep() -> list[ExperimentVariant]:
    """稀缺保护强度扫描。

    测试 w_scarcity 从 0 到 160 的不同取值。
    """
    values = [0.0, 10.0, 20.0, 40.0, 80.0, 160.0]
    variants: list[ExperimentVariant] = []
    for v in values:
        label = "关闭稀缺保护" if v == 0.0 else f"w_scarcity = {v:.0f}"
        variants.append(
            ExperimentVariant(
                name=f"scarcity_{v:.0f}",
                label=label,
                description=f"稀缺保护权重设为 {v}",
                overrides={"w_scarcity": str(v)},
            )
        )
    return variants


EXPERIMENT_REGISTRY = {
    "task_ablation": ("任务评分组件消融", make_task_ablation),
    "server_ablation": ("服务器评分组件消融", make_server_ablation),
    "version_compare": ("V0/V1a/V1b 三阶段对比", make_version_compare),
    "scarcity_sweep": ("稀缺保护强度扫描", make_scarcity_sweep),
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class VariantResult:
    """一个实验变体在所有实例上的汇总结果。"""
    name: str
    label: str
    description: str
    total_cases: int = 0
    passed: int = 0
    avg_e_wait: float = 0.0
    avg_e_memory: float = 0.0
    avg_e_finish: float = 0.0
    total_elapsed_sec: float = 0.0
    per_case: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_cases if self.total_cases else 0.0


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------
def write_config(params: dict[str, str], path: Path) -> None:
    lines = [f"# ablation config"]
    for key, value in params.items():
        lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_one(
    input_path: Path,
    scheduler_path: Path,
    validator_path: Path,
    config_file: Path | None,
    preset: str,
    timeout_sec: int,
) -> dict[str, Any]:
    """运行单个实例，返回结果字典。"""
    case_name = input_path.stem
    start = time.perf_counter()

    # 构建环境变量
    import os
    env = dict(os.environ)
    if preset:
        env["SCHEDULER_CONFIG"] = preset
    elif config_file:
        env["SCHEDULER_CONFIG"] = "custom"
        env["SCHEDULER_CONFIG_FILE"] = str(config_file.resolve())
    else:
        return {
            "case": case_name, "exit_code": -9, "elapsed": 0.0,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": "no config specified",
        }

    try:
        with input_path.open("r", encoding="utf-8") as src:
            proc = subprocess.run(
                [str(scheduler_path)],
                stdin=src,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                text=True, encoding="utf-8",
                env=env,
            )
    except subprocess.TimeoutExpired:
        return {
            "case": case_name, "exit_code": -1,
            "elapsed": time.perf_counter() - start,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": f"timeout ({timeout_sec}s)",
        }
    except FileNotFoundError:
        return {
            "case": case_name, "exit_code": -2,
            "elapsed": time.perf_counter() - start,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": f"scheduler not found: {scheduler_path}",
        }

    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        return {
            "case": case_name, "exit_code": proc.returncode,
            "elapsed": elapsed, "valid": False,
            "e_wait": 0.0, "e_memory": 0.0, "e_finish": 0.0,
            "error": proc.stderr.strip()[:500] or f"exit {proc.returncode}",
        }

    output = proc.stdout
    if not output.strip():
        return {
            "case": case_name, "exit_code": 0, "elapsed": elapsed,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": "empty output",
        }

    # 验证
    try:
        validator_input = (
            input_path.read_text(encoding="utf-8").rstrip() + "\n" + output
        )
        vproc = subprocess.run(
            [str(validator_path), "--quiet"],
            input=validator_input,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout_sec, text=True, encoding="utf-8",
        )
        stdout = vproc.stdout.strip()
        if not stdout:
            return {
                "case": case_name, "exit_code": 0, "elapsed": elapsed,
                "valid": False, "e_wait": 0.0, "e_memory": 0.0,
                "e_finish": 0.0, "error": "validator no output",
            }
        payload = json.loads(stdout)
        valid = bool(payload.get("valid", False))
        if not valid:
            return {
                "case": case_name, "exit_code": 0, "elapsed": elapsed,
                "valid": False, "e_wait": 0.0, "e_memory": 0.0,
                "e_finish": 0.0,
                "error": f"invalid: {payload.get('errors', '?')} errors",
            }
        return {
            "case": case_name, "exit_code": 0, "elapsed": elapsed,
            "valid": True,
            "e_wait": float(payload["E_wait"]),
            "e_memory": float(payload["E_memory"]),
            "e_finish": float(payload["E_finish"]),
            "error": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "case": case_name, "exit_code": 0, "elapsed": elapsed,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": "validator timeout",
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "case": case_name, "exit_code": 0, "elapsed": elapsed,
            "valid": False, "e_wait": 0.0, "e_memory": 0.0,
            "e_finish": 0.0, "error": f"validator JSON: {exc}",
        }


def run_experiment(
    variants: list[ExperimentVariant],
    instances: list[Path],
    scheduler_path: Path,
    validator_path: Path,
    timeout_sec: int,
) -> list[VariantResult]:
    """运行一组实验变体。"""
    results: list[VariantResult] = []
    config_dir = Path("/tmp/ablation_configs")
    config_dir.mkdir(parents=True, exist_ok=True)

    for vi, variant in enumerate(variants):
        result = VariantResult(
            name=variant.name,
            label=variant.label,
            description=variant.description,
            total_cases=len(instances),
        )

        # 准备配置
        config_file: Path | None = None
        preset = variant.use_preset
        if not preset:
            params = dict(DEFAULT_PARAMS)
            params.update(variant.overrides)
            config_file = config_dir / f"{variant.name}.txt"
            write_config(params, config_file)

        print(f"\n{'=' * 60}")
        print(f"[{vi + 1}/{len(variants)}] {variant.label}")
        print(f"     {variant.description}")
        print(f"{'=' * 60}")

        for ci, input_path in enumerate(instances):
            case_result = run_one(
                input_path, scheduler_path, validator_path,
                config_file, preset, timeout_sec,
            )

            result.per_case[case_result["case"]] = case_result

            if case_result["valid"]:
                result.passed += 1
                result.avg_e_wait += case_result["e_wait"]
                result.avg_e_memory += case_result["e_memory"]
                result.avg_e_finish += case_result["e_finish"]
            result.total_elapsed_sec += case_result["elapsed"]

            status = "PASS" if case_result["valid"] else "FAIL"
            wait_str = f"E_wait={case_result['e_wait']:.4f}" if case_result["valid"] else ""
            print(
                f"  [{ci + 1:>3}/{len(instances)}] "
                f"{case_result['case']:<16} {status} "
                f"({case_result['elapsed']:.2f}s"
                f"{', ' + wait_str if wait_str else ''})"
            )

        if result.passed > 0:
            result.avg_e_wait /= result.passed
            result.avg_e_memory /= result.passed
            result.avg_e_finish /= result.passed

        results.append(result)

    return results


def compute_delta(baseline: VariantResult, variant: VariantResult) -> dict[str, float]:
    """计算变体相对基线的变化百分比。正值 = 变差，负值 = 改善。"""
    if baseline.passed == 0 or variant.passed == 0:
        return {"e_wait_pct": 0.0, "e_memory_pct": 0.0, "e_finish_pct": 0.0}
    return {
        "e_wait_pct": _pct_change(baseline.avg_e_wait, variant.avg_e_wait),
        "e_memory_pct": _pct_change(baseline.avg_e_memory, variant.avg_e_memory),
        "e_finish_pct": _pct_change(baseline.avg_e_finish, variant.avg_e_finish),
    }


def _pct_change(base: float, variant: float) -> float:
    if base == 0.0:
        return 0.0 if variant == 0.0 else 100.0
    return (variant - base) / base * 100.0


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------
def print_comparison_table(
    title: str,
    results: list[VariantResult],
    baseline_name: str = "baseline_v1b",
) -> None:
    """打印对比表格。"""
    # 找基线
    baseline = next((r for r in results if r.name == baseline_name), None)
    if baseline is None and results:
        baseline = results[0]

    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")
    header = (
        f"{'变体':<30} {'通过':<8} {'E_wait':>16} {'E_memory':>14} "
        f"{'E_finish':>14} {'ΔE_wait':>10} {'ΔE_mem':>10}"
    )
    print(header)
    print("-" * 80)

    for r in results:
        delta = compute_delta(baseline, r) if baseline else {}
        dw = f"{delta.get('e_wait_pct', 0):+.1f}%"
        dm = f"{delta.get('e_memory_pct', 0):+.1f}%"
        print(
            f"{r.label:<30} {f'{r.passed}/{r.total_cases}':<8} "
            f"{r.avg_e_wait:>16.6f} {r.avg_e_memory:>14.4f} "
            f"{r.avg_e_finish:>14.4f} {dw:>10} {dm:>10}"
        )

    print("-" * 80)
    if baseline:
        print(f"  基线: {baseline.label}")
        print(f"  Δ 正值 = 比基线差，负值 = 比基线好")
    print(f"{'=' * 80}")


def export_csv(results: list[VariantResult], path: Path) -> None:
    """导出实验结果为 CSV。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = results[0] if results else None
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name", "label", "passed", "total", "pass_rate",
            "avg_e_wait", "avg_e_memory", "avg_e_finish",
            "delta_e_wait_pct", "delta_e_memory_pct", "delta_e_finish_pct",
            "total_elapsed_sec", "description",
        ])
        for r in results:
            delta = compute_delta(baseline, r) if baseline else {}
            writer.writerow([
                r.name, r.label, r.passed, r.total_cases,
                f"{r.pass_rate:.4f}",
                f"{r.avg_e_wait:.6f}" if r.passed > 0 else "",
                f"{r.avg_e_memory:.6f}" if r.passed > 0 else "",
                f"{r.avg_e_finish:.6f}" if r.passed > 0 else "",
                f"{delta.get('e_wait_pct', 0):.2f}",
                f"{delta.get('e_memory_pct', 0):.2f}",
                f"{delta.get('e_finish_pct', 0):.2f}",
                f"{r.total_elapsed_sec:.2f}",
                r.description,
            ])
    print(f"CSV 已导出: {path}")


def generate_markdown_report(
    output_dir: Path,
    all_results: dict[str, list[VariantResult]],
) -> Path:
    """生成完整的 Markdown 实验报告。"""
    report_path = output_dir / "ablation_report.md"
    lines: list[str] = []
    lines.append(f"# V1 消融实验报告")
    lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    for exp_name, (exp_title, _) in EXPERIMENT_REGISTRY.items():
        results = all_results.get(exp_name)
        if not results:
            continue

        lines.append(f"## {exp_title}\n")

        baseline = results[0]
        lines.append(f"基线: **{baseline.label}**")
        lines.append(f"(pass={baseline.passed}/{baseline.total_cases}, "
                     f"E_wait={baseline.avg_e_wait:.6f}, "
                     f"E_memory={baseline.avg_e_memory:.4f})\n")

        lines.append("| 变体 | 通过 | E_wait | E_memory | E_finish | ΔE_wait | ΔE_mem |")
        lines.append("|------|------|--------|----------|----------|---------|--------|")

        for r in results:
            delta = compute_delta(baseline, r)
            dw = f"{delta.get('e_wait_pct', 0):+.1f}%"
            dm = f"{delta.get('e_memory_pct', 0):+.1f}%"
            lines.append(
                f"| {r.label} | {r.passed}/{r.total_cases} | "
                f"{r.avg_e_wait:.4f} | {r.avg_e_memory:.4f} | "
                f"{r.avg_e_finish:.4f} | {dw} | {dm} |"
            )

        # 找出影响最大的组件
        non_baseline = [r for r in results if r.name != baseline.name]
        if non_baseline:
            worst_wait = max(non_baseline, key=lambda r: r.avg_e_wait if r.passed > 0 else float("inf"))
            worst_mem = max(non_baseline, key=lambda r: r.avg_e_memory if r.passed > 0 else float("inf"))
            lines.append(f"\n**关键发现:**")
            lines.append(f"- 对 E_wait 影响最大: **{worst_wait.label}**")
            lines.append(f"- 对 E_memory 影响最大: **{worst_mem.label}**")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="消融实验工具 —— 自动对照组 + 对比分析"
    )
    parser.add_argument(
        "instances_dir", type=Path, nargs="?",
        default=DEFAULT_INSTANCES, help="实例目录",
    )
    parser.add_argument(
        "--experiment", type=str, default="task_ablation",
        choices=["task_ablation", "server_ablation", "version_compare",
                 "scarcity_sweep", "all"],
        help="实验类型（默认 task_ablation）",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="快速模式：只跑代表性实例",
    )
    parser.add_argument(
        "--timeout", type=int, default=60, help="单实例超时秒数",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="输出目录",
    )
    parser.add_argument(
        "--scheduler", type=Path, default=DEFAULT_SCHEDULER,
    )
    parser.add_argument(
        "--validator", type=Path, default=DEFAULT_VALIDATOR,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 校验路径
    instances_dir = args.instances_dir.resolve()
    scheduler_path = args.scheduler.resolve()
    validator_path = args.validator.resolve()
    if not instances_dir.is_dir():
        print(f"实例目录不存在: {instances_dir}", file=sys.stderr)
        return 2
    if not scheduler_path.is_file():
        print(f"调度器不存在: {scheduler_path}", file=sys.stderr)
        return 2
    if not validator_path.is_file():
        print(f"验证器不存在: {validator_path}", file=sys.stderr)
        return 2

    # 实例列表
    if args.quick:
        quick_set = set(QUICK_INSTANCES)
        instances = sorted(
            [p for p in instances_dir.glob("*.in") if p.stem in quick_set],
            key=lambda p: QUICK_INSTANCES.index(p.stem)
            if p.stem in quick_set else 999,
        )
    else:
        instances = sorted(instances_dir.glob("*.in"))
    if not instances:
        print(f"未找到 .in 文件", file=sys.stderr)
        return 2

    # 输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else PROJECT_ROOT / "experiments" / "ablation" / f"run_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # 选择实验
    if args.experiment == "all":
        experiments_to_run = list(EXPERIMENT_REGISTRY.keys())
    else:
        experiments_to_run = [args.experiment]

    mode = "快速" if args.quick else "完整"
    print(f"消融实验工具")
    print(f"  实验:   {', '.join(experiments_to_run)}")
    print(f"  模式:   {mode} ({len(instances)} 个实例)")
    print(f"  输出:   {output_dir}")
    print(f"  超时:   {args.timeout}s")

    all_results: dict[str, list[VariantResult]] = {}
    total_start = time.perf_counter()

    for exp_name in experiments_to_run:
        exp_title, factory = EXPERIMENT_REGISTRY[exp_name]
        variants = factory()
        print(f"\n{'#' * 60}")
        print(f"# 实验: {exp_title} ({len(variants)} 个变体)")
        print(f"{'#' * 60}")

        results = run_experiment(
            variants, instances, scheduler_path, validator_path, args.timeout,
        )
        all_results[exp_name] = results

        # 打印对比表
        print_comparison_table(exp_title, results)

        # 导出 CSV
        csv_path = output_dir / f"{exp_name}.csv"
        export_csv(results, csv_path)

    # 生成 Markdown 报告
    report_path = generate_markdown_report(output_dir, all_results)
    print(f"\n报告: {report_path}")

    total_sec = time.perf_counter() - total_start
    print(f"\n全部实验完成，总耗时 {total_sec:.0f}s ({total_sec/60:.1f}min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
