#!/usr/bin/env python3
"""多起点构造运行器 —— 遍历参数组合，对100个实例逐一运行，保留最优配置。

用法：
    # 使用内置默认网格，跑全部实例
    python3 tools/multi_start_runner.py instances/

    # 快速模式：只跑代表性实例（简单+极端）
    python3 tools/multi_start_runner.py instances/ --quick

    # 从 CSV 加载自定义参数网格
    python3 tools/multi_start_runner.py instances/ --config-grid my_grid.csv
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
# 项目根目录（本脚本位于 tools/ 下）
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEDULER = PROJECT_ROOT / "build" / "scheduler"
DEFAULT_VALIDATOR = PROJECT_ROOT / "build" / "validator"
DEFAULT_INSTANCES = PROJECT_ROOT / "instances"


# ---------------------------------------------------------------------------
# 参数网格定义
# ---------------------------------------------------------------------------
# 每个参数： (标签, 配置文件key, 默认值, [候选值列表])
# 候选值用于 grid search；也可以修改后从 CSV 加载
PARAM_SPACE: list[tuple[str, str, str, list[Any]]] = [
    # Task scoring
    ("task_scoring", "task_scoring_enabled", "true", ["true"]),
    ("w_priority",   "w_priority",   "2.0",  ["1.0", "2.0", "4.0", "8.0"]),
    ("w_wait",       "w_wait",       "0.01", ["0.001", "0.01", "0.1", "1.0"]),
    ("w_scarcity",   "w_scarcity",   "40.0", ["10.0", "20.0", "40.0", "80.0"]),
    ("w_area",       "w_area",       "0.20", ["0.05", "0.10", "0.20", "0.40"]),
    ("w_short_job",  "w_short_job",  "4.0",  ["1.0", "2.0", "4.0", "8.0"]),
    # Server scoring
    ("server_mode",  "server_mode",  "weighted", ["weighted"]),
    ("w_gpu_fragment",        "w_gpu_fragment",        "4.0", ["1.0", "2.0", "4.0", "8.0"]),
    ("w_gpu_memory_fragment", "w_gpu_memory_fragment", "2.0", ["1.0", "2.0", "4.0"]),
    ("w_cpu_fragment",        "w_cpu_fragment",        "1.0", ["0.5", "1.0", "2.0"]),
    ("w_memory_fragment",     "w_memory_fragment",     "1.0", ["0.5", "1.0", "2.0"]),
]

# 快速模式使用的代表性实例（覆盖四档难度）
QUICK_INSTANCES: list[str] = [
    "case001", "case002", "case003", "case004",   # 简单
    "case011", "case012", "case013",                # 中等（采样）
    "case021", "case051", "case081",                # 困难（采样）
    "case091", "case095", "case098", "case100",     # 极端
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class ConfigResult:
    """一组参数在所有实例上的汇总结果。"""
    config_id: str
    params: dict[str, str]
    total_cases: int = 0
    passed: int = 0
    avg_e_wait: float = 0.0
    avg_e_memory: float = 0.0
    avg_e_finish: float = 0.0
    total_elapsed_sec: float = 0.0
    failed_cases: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_cases if self.total_cases else 0.0


@dataclass
class CaseResult:
    """单个实例的单次运行结果。"""
    case_name: str
    exit_code: int = 0
    elapsed_sec: float = 0.0
    is_legal: bool = False
    e_wait: float = 0.0
    e_memory: float = 0.0
    e_finish: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def generate_grid() -> list[dict[str, str]]:
    """从 PARAM_SPACE 生成笛卡尔积网格。

    为避免组合爆炸，只对核心参数做网格搜索，其余用默认值。
    核心参数：w_priority, w_wait, w_scarcity, w_gpu_fragment
    预估组合数：4 × 4 × 4 × 4 = 256
    """
    # 只对关键维度做笛卡尔积
    sweep_keys = {"w_priority", "w_wait", "w_scarcity", "w_gpu_fragment"}
    sweeps: dict[str, list[str]] = {}
    defaults: dict[str, str] = {}

    for label, key, default, candidates in PARAM_SPACE:
        if key in sweep_keys:
            sweeps[key] = [str(v) for v in candidates]
        else:
            defaults[key] = default

    configs: list[dict[str, str]] = []
    _cartesian_product(sweeps, defaults, configs)
    return configs


def _cartesian_product(
    sweeps: dict[str, list[str]],
    base: dict[str, str],
    out: list[dict[str, str]],
    keys: list[str] | None = None,
    current: dict[str, str] | None = None,
) -> None:
    """递归生成笛卡尔积。"""
    if keys is None:
        keys = list(sweeps.keys())
    if current is None:
        current = {}

    if not keys:
        config = dict(base)
        config.update(current)
        out.append(config)
        return

    key = keys[0]
    for value in sweeps[key]:
        current[key] = value
        _cartesian_product(sweeps, base, out, keys[1:], current)


def generate_grid_csv(path: Path) -> None:
    """生成默认参数网格 CSV 文件，方便手动编辑。"""
    configs = generate_grid()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(configs[0].keys()))
        for config in configs:
            writer.writerow(list(config.values()))
    print(f"参数网格已写入: {path} ({len(configs)} 组)")


def load_grid_csv(path: Path) -> list[dict[str, str]]:
    """从 CSV 文件加载参数网格。"""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_config_file(params: dict[str, str], path: Path) -> None:
    """将参数字典写入 C++ 可读的配置文件。"""
    lines = [f"# multi-start config\n"]
    for key, value in params.items():
        lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run_one_case(
    input_path: Path,
    scheduler_path: Path,
    config_file: Path,
    timeout_sec: int,
) -> CaseResult:
    """用指定配置运行单个实例。"""
    result = CaseResult(case_name=input_path.stem)
    start = time.perf_counter()

    try:
        env = {
            "SCHEDULER_CONFIG": "custom",
            "SCHEDULER_CONFIG_FILE": str(config_file.resolve()),
        }
        with input_path.open("r", encoding="utf-8") as source:
            process = subprocess.run(
                [str(scheduler_path)],
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
                text=True,
                encoding="utf-8",
                env={**__import__("os").environ, **env},
            )
        result.elapsed_sec = time.perf_counter() - start
        result.exit_code = process.returncode
        result.output = process.stdout

        if process.returncode != 0:
            result.error = process.stderr.strip()[:500] or f"exit {process.returncode}"
            return result

        # 行数检查
        lines = [l for l in process.stdout.splitlines() if l.strip()]
        if not lines:
            result.error = "empty output"
            return result
        result.output_lines = len(lines)

    except subprocess.TimeoutExpired:
        result.elapsed_sec = time.perf_counter() - start
        result.exit_code = -1
        result.error = f"timeout ({timeout_sec}s)"
    except FileNotFoundError:
        result.exit_code = -2
        result.error = f"scheduler not found: {scheduler_path}"
    except Exception as exc:
        result.exit_code = -3
        result.error = str(exc)[:500]

    return result


def validate_output(
    input_path: Path,
    output_text: str,
    validator_path: Path,
    timeout_sec: int,
) -> tuple[bool, float, float, float, str]:
    """验证调度输出，返回 (valid, e_wait, e_memory, e_finish, error)。"""
    try:
        validator_input = (
            input_path.read_text(encoding="utf-8").rstrip()
            + "\n"
            + output_text
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
            return False, 0.0, 0.0, 0.0, "validator produced no output"

        payload = json.loads(stdout)
        valid = bool(payload.get("valid", False))
        if not valid:
            errors = payload.get("errors", "unknown")
            return False, 0.0, 0.0, 0.0, f"invalid: {errors} errors"

        return (
            True,
            float(payload["E_wait"]),
            float(payload["E_memory"]),
            float(payload["E_finish"]),
            "",
        )
    except subprocess.TimeoutExpired:
        return False, 0.0, 0.0, 0.0, "validator timeout"
    except FileNotFoundError:
        return False, 0.0, 0.0, 0.0, f"validator not found: {validator_path}"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return False, 0.0, 0.0, 0.0, f"validator JSON error: {exc}"
    except Exception as exc:
        return False, 0.0, 0.0, 0.0, str(exc)[:500]


def resolve_instances(
    instances_dir: Path,
    quick: bool,
) -> list[Path]:
    """获取要运行的实例列表。"""
    all_cases = sorted(instances_dir.glob("*.in"))
    if not all_cases:
        return []

    if not quick:
        return all_cases

    # 快速模式：只跑代表性实例
    quick_set = set(QUICK_INSTANCES)
    selected = [p for p in all_cases if p.stem in quick_set]
    # 保持 QUICK_INSTANCES 的顺序
    selected.sort(key=lambda p: QUICK_INSTANCES.index(p.stem)
                  if p.stem in quick_set else 999)
    return selected


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_config_sweep(
    configs: list[dict[str, str]],
    instances: list[Path],
    scheduler_path: Path,
    validator_path: Path,
    output_dir: Path,
    timeout_sec: int,
) -> list[ConfigResult]:
    """遍历所有参数组合，对每个实例运行并收集结果。"""
    config_results: list[ConfigResult] = []

    for config_index, params in enumerate(configs):
        config_id = f"cfg_{config_index:04d}"
        config_file = output_dir / "configs" / f"{config_id}.txt"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        write_config_file(params, config_file)

        result = ConfigResult(
            config_id=config_id,
            params=params,
            total_cases=len(instances),
        )

        print(f"\n{'=' * 60}")
        print(f"[{config_index + 1}/{len(configs)}] {config_id}")
        print(f"     params: {params}")
        print(f"{'=' * 60}")

        for case_index, input_path in enumerate(instances):
            case_result = run_one_case(
                input_path, scheduler_path, config_file, timeout_sec
            )

            if case_result.exit_code == 0 and case_result.output:
                valid, e_wait, e_memory, e_finish, err = validate_output(
                    input_path,
                    case_result.output,
                    validator_path,
                    timeout_sec,
                )
                case_result.is_legal = valid
                case_result.e_wait = e_wait
                case_result.e_memory = e_memory
                case_result.e_finish = e_finish
                if err:
                    case_result.error = err
            else:
                case_result.is_legal = False

            # 汇总
            if case_result.is_legal:
                result.passed += 1
                result.avg_e_wait += case_result.e_wait
                result.avg_e_memory += case_result.e_memory
                result.avg_e_finish += case_result.e_finish
            else:
                result.failed_cases.append(case_result.case_name)

            result.total_elapsed_sec += case_result.elapsed_sec

            status = "PASS" if case_result.is_legal else "FAIL"
            print(
                f"  [{case_index + 1:>3}/{len(instances)}] "
                f"{case_result.case_name:<16} {status} "
                f"({case_result.elapsed_sec:.2f}s"
                f"{f', E_wait={case_result.e_wait:.4f}' if case_result.is_legal else ''})"
            )

        # 计算均值
        if result.passed > 0:
            result.avg_e_wait /= result.passed
            result.avg_e_memory /= result.passed
            result.avg_e_finish /= result.passed

        config_results.append(result)

        # 中间摘要
        print(f"\n--- {config_id} 汇总 ---")
        print(f"  通过: {result.passed}/{result.total_cases}")
        if result.passed > 0:
            print(f"  平均 E_wait:   {result.avg_e_wait:.6f}")
            print(f"  平均 E_memory: {result.avg_e_memory:.6f}")
            print(f"  平均 E_finish: {result.avg_e_finish:.6f}")
        if result.failed_cases:
            print(f"  失败: {', '.join(result.failed_cases[:10])}"
                  f"{'...' if len(result.failed_cases) > 10 else ''}")

    return config_results


def export_ranking(
    config_results: list[ConfigResult],
    output_dir: Path,
) -> None:
    """输出配置排名 CSV（按平均 E_wait 升序）。"""
    sorted_results = sorted(
        config_results,
        key=lambda r: r.avg_e_wait if r.passed > 0 else float("inf"),
    )

    csv_path = output_dir / "config_ranking.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        # 列：排名 + 所有参数 + 汇总指标
        param_keys = list(config_results[0].params.keys()) if config_results else []
        header = (
            ["rank", "config_id", "passed", "total", "pass_rate",
             "avg_e_wait", "avg_e_memory", "avg_e_finish",
             "total_elapsed_sec"]
            + param_keys
        )
        writer = csv.writer(f)
        writer.writerow(header)

        for rank, result in enumerate(sorted_results, 1):
            row = [
                rank,
                result.config_id,
                result.passed,
                result.total_cases,
                f"{result.pass_rate:.4f}",
                f"{result.avg_e_wait:.6f}" if result.passed > 0 else "",
                f"{result.avg_e_memory:.6f}" if result.passed > 0 else "",
                f"{result.avg_e_finish:.6f}" if result.passed > 0 else "",
                f"{result.total_elapsed_sec:.2f}",
            ]
            for key in param_keys:
                row.append(result.params.get(key, ""))
            writer.writerow(row)

    print(f"\n排名 CSV: {csv_path}")

    # 打印 Top 5
    print(f"\n{'=' * 60}")
    print("Top 5 配置")
    print(f"{'=' * 60}")
    for rank, result in enumerate(sorted_results[:5], 1):
        print(
            f"  #{rank} {result.config_id}: "
            f"pass={result.passed}/{result.total_cases}, "
            f"E_wait={result.avg_e_wait:.6f}, "
            f"E_memory={result.avg_e_memory:.4f}"
        )
        # 打印关键参数
        key_params = ["w_priority", "w_wait", "w_scarcity", "w_gpu_fragment"]
        print(f"      " + "  ".join(
            f"{k}={result.params.get(k, '?')}" for k in key_params
        ))


def print_best_config_file(config_results: list[ConfigResult]) -> None:
    """打印最优配置的内容，方便直接复制为 scheduler_config.txt。"""
    if not config_results:
        return

    best = min(
        config_results,
        key=lambda r: r.avg_e_wait if r.passed > 0 else float("inf"),
    )

    print(f"\n{'=' * 60}")
    print(f"最优配置: {best.config_id}")
    print(f"  E_wait={best.avg_e_wait:.6f}, pass={best.passed}/{best.total_cases}")
    print(f"{'=' * 60}")
    print("# 将以下内容保存为 scheduler_config.txt 即可复现最优结果：")
    print()
    for key, value in best.params.items():
        print(f"{key} = {value}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="多起点构造运行器 —— 参数网格搜索 + 批量验证"
    )
    parser.add_argument(
        "instances_dir", type=Path, nargs="?",
        default=DEFAULT_INSTANCES,
        help="实例目录（默认: instances/）",
    )
    parser.add_argument(
        "--config-grid", type=Path, default=None,
        help="从 CSV 加载参数网格（不指定则自动生成默认网格）",
    )
    parser.add_argument(
        "--generate-grid", type=Path, default=None,
        help="生成默认参数网格 CSV 并退出",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="快速模式：只跑代表性实例（约14个）",
    )
    parser.add_argument(
        "--timeout", type=int, default=60,
        help="单个实例超时秒数（默认 60）",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="输出目录（默认: experiments/results/ms_<timestamp>）",
    )
    parser.add_argument(
        "--scheduler", type=Path, default=DEFAULT_SCHEDULER,
        help="调度器路径",
    )
    parser.add_argument(
        "--validator", type=Path, default=DEFAULT_VALIDATOR,
        help="验证器路径",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 只生成网格 CSV
    if args.generate_grid:
        generate_grid_csv(args.generate_grid)
        return 0

    # 路径校验
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

    # 加载或生成参数网格
    if args.config_grid:
        configs = load_grid_csv(args.config_grid.resolve())
        print(f"从 CSV 加载了 {len(configs)} 组参数")
    else:
        configs = generate_grid()
        print(f"使用默认参数网格: {len(configs)} 组参数")

    if not configs:
        print("参数网格为空", file=sys.stderr)
        return 2

    # 实例列表
    instances = resolve_instances(instances_dir, args.quick)
    if not instances:
        print(f"未找到 .in 文件: {instances_dir}", file=sys.stderr)
        return 2

    # 输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else PROJECT_ROOT / "experiments" / "results" / f"ms_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = "快速" if args.quick else "完整"
    print(f"多起点构造运行器")
    print(f"  模式:       {mode} ({len(instances)} 个实例)")
    print(f"  参数组合:   {len(configs)} 组")
    print(f"  实例目录:   {instances_dir}")
    print(f"  输出目录:   {output_dir}")
    print(f"  调度器:     {scheduler_path}")
    print(f"  验证器:     {validator_path}")
    print(f"  超时:       {args.timeout}s")

    # 预估时间
    est_minutes = (len(configs) * len(instances) * args.timeout) / 60
    print(f"  预估最长:   {est_minutes:.0f} 分钟")

    start_time = time.perf_counter()

    config_results = run_config_sweep(
        configs, instances, scheduler_path, validator_path,
        output_dir, args.timeout,
    )

    total_sec = time.perf_counter() - start_time

    # 输出排名
    export_ranking(config_results, output_dir)
    print_best_config_file(config_results)

    # 总体摘要
    print(f"\n{'=' * 60}")
    print(f"全部完成")
    print(f"{'=' * 60}")
    print(f"  参数组合: {len(config_results)}")
    print(f"  总耗时:   {total_sec:.0f}s ({total_sec/60:.1f}min)")
    print(f"  结果目录: {output_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
