#!/usr/bin/env python3
"""版本对比工具 —— 比较两次实验运行的结果。

用法：
  python3 compare_versions.py <old_csv_or_dir> <new_csv_or_dir>

说明：
  - 可以传入两个 batch_summary.csv 文件
  - 也可以传入两个 results 目录（自动读取 .meta 文件）

输出：
  - 逐实例对比表
  - 三项指标变化汇总
  - 改进最大 / 退化最大的实例
"""

import csv
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class InstanceMetrics:
    """单个实例的运行指标"""
    case_name: str
    exit_code: int = 0
    elapsed_sec: float = 0.0
    is_legal: bool = True
    e_wait: Optional[float] = None
    e_memory: Optional[float] = None
    e_finish: Optional[float] = None


@dataclass
class DiffEntry:
    """一个实例的对比差异"""
    case_name: str
    old: InstanceMetrics
    new: InstanceMetrics

    # 差异（负值 = 改善，正值 = 退化）
    delta_wait: float = 0.0     # E_wait 变化
    delta_memory: float = 0.0   # E_memory 变化
    delta_finish: float = 0.0   # E_finish 变化
    delta_time: float = 0.0     # 运行时间变化
    regressed: bool = False     # 是否退化（任一指标变差）
    improved: bool = False      # 是否改善（任一指标变好）


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

def read_from_csv(csv_path: str) -> Dict[str, InstanceMetrics]:
    """从 batch_summary.csv 读取指标"""
    result: Dict[str, InstanceMetrics] = {}
    if not os.path.exists(csv_path):
        print(f"[警告] 文件不存在: {csv_path}")
        return result

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("实例", "")
            if not name:
                continue

            m = InstanceMetrics(case_name=name)

            try:
                m.exit_code = int(row.get("退出码", 0))
            except (ValueError, TypeError):
                pass

            try:
                m.elapsed_sec = float(row.get("耗时(s)", 0))
            except (ValueError, TypeError):
                pass

            # 合法性
            legal_val = row.get("合法", "")
            m.is_legal = (legal_val == "1" or legal_val.lower() == "true")

            # 三项指标
            for key, attr in [("E_wait", "e_wait"), ("E_memory", "e_memory"), ("E_finish", "e_finish")]:
                val = row.get(key, "")
                if val:
                    try:
                        setattr(m, attr, float(val))
                    except ValueError:
                        pass

            result[name] = m
    return result


def read_from_meta_dir(dir_path: str) -> Dict[str, InstanceMetrics]:
    """从 experiment results 目录读取 .meta 文件"""
    result: Dict[str, InstanceMetrics] = {}
    if not os.path.isdir(dir_path):
        print(f"[警告] 目录不存在: {dir_path}")
        return result

    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith(".meta"):
            continue
        meta_path = os.path.join(dir_path, fname)
        case_name = fname.replace(".meta", ".in")

        m = InstanceMetrics(case_name=case_name)
        with open(meta_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("exit_code="):
                    try:
                        m.exit_code = int(line.split("=", 1)[1])
                    except ValueError:
                        pass
                elif line.startswith("elapsed_sec="):
                    try:
                        m.elapsed_sec = float(line.split("=", 1)[1])
                    except ValueError:
                        pass
                elif line.startswith("timed_out="):
                    if line.split("=", 1)[1] == "True":
                        m.exit_code = -1
        result[case_name] = m
    return result


def auto_read(path: str) -> Dict[str, InstanceMetrics]:
    """自动识别 CSV 文件或目录"""
    if os.path.isfile(path) and path.endswith(".csv"):
        return read_from_csv(path)
    elif os.path.isdir(path):
        return read_from_meta_dir(path)
    else:
        print(f"[错误] 无法识别路径类型: {path}")
        return {}


# ---------------------------------------------------------------------------
# 对比
# ---------------------------------------------------------------------------

def compare(old_metrics: Dict[str, InstanceMetrics],
            new_metrics: Dict[str, InstanceMetrics]) -> List[DiffEntry]:
    """逐实例对比"""
    all_cases = sorted(set(old_metrics.keys()) | set(new_metrics.keys()))
    diffs: List[DiffEntry] = []

    for case in all_cases:
        old = old_metrics.get(case)
        new = new_metrics.get(case)

        if old is None:
            print(f"[跳过] {case}: 旧版本无数据")
            continue
        if new is None:
            print(f"[跳过] {case}: 新版本无数据")
            continue

        entry = DiffEntry(case_name=case, old=old, new=new)

        # 计算差异
        entry.delta_time = new.elapsed_sec - old.elapsed_sec

        # 三项指标：需要双方都有数据
        for attr, delta_attr in [("e_wait", "delta_wait"),
                                  ("e_memory", "delta_memory"),
                                  ("e_finish", "delta_finish")]:
            ov = getattr(old, attr)
            nv = getattr(new, attr)
            if ov is not None and nv is not None:
                setattr(entry, delta_attr, nv - ov)

        # 判断改善/退化（越小越好）
        has_improvement = (
            entry.delta_wait < 0 or
            entry.delta_memory < 0 or
            entry.delta_finish < 0
        )
        has_regression = (
            entry.delta_wait > 0 or
            entry.delta_memory > 0 or
            entry.delta_finish > 0
        )

        # 合法性变化
        if not old.is_legal and new.is_legal:
            has_improvement = True
        if old.is_legal and not new.is_legal:
            has_regression = True

        entry.improved = has_improvement
        entry.regressed = has_regression

        diffs.append(entry)

    return diffs


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def print_comparison(diffs: List[DiffEntry]):
    """打印对比结果"""
    if not diffs:
        print("没有可对比的实例")
        return

    # 合法性
    legal_old = sum(1 for d in diffs if d.old.is_legal)
    legal_new = sum(1 for d in diffs if d.new.is_legal)

    # 筛选有指标数据的
    with_wait = [d for d in diffs if d.old.e_wait is not None and d.new.e_wait is not None]
    with_mem = [d for d in diffs if d.old.e_memory is not None and d.new.e_memory is not None]
    with_finish = [d for d in diffs if d.old.e_finish is not None and d.new.e_finish is not None]

    improved = [d for d in diffs if d.improved]
    regressed = [d for d in diffs if d.regressed]

    print("=" * 70)
    print("版本对比汇总")
    print("=" * 70)

    print(f"\n  合法性: {legal_old} → {legal_new} "
          f"({'持平' if legal_old == legal_new else ('+' + str(legal_new - legal_old) if legal_new > legal_old else str(legal_new - legal_old))})")

    if with_wait:
        avg_dw = sum(d.delta_wait for d in with_wait) / len(with_wait)
        print(f"  E_wait  平均变化: {avg_dw:+.4f}  ({len(with_wait)} 个可比实例)")

    if with_mem:
        avg_dm = sum(d.delta_memory for d in with_mem) / len(with_mem)
        print(f"  E_memory 平均变化: {avg_dm:+.4f}  ({len(with_mem)} 个可比实例)")

    if with_finish:
        avg_df = sum(d.delta_finish for d in with_finish) / len(with_finish)
        print(f"  E_finish 平均变化: {avg_df:+.4f}  ({len(with_finish)} 个可比实例)")

    # 运行时间
    time_diffs = [d for d in diffs if d.old.elapsed_sec > 0 and d.new.elapsed_sec > 0]
    if time_diffs:
        avg_dt = sum(d.delta_time for d in time_diffs) / len(time_diffs)
        print(f"  运行时间平均变化: {avg_dt:+.3f}s")

    print(f"\n  改善实例: {len(improved)}")
    print(f"  退化实例: {len(regressed)}")
    print(f"  无变化:   {len(diffs) - len(set(d.id for d in improved) | set(d.id for d in regressed))}")

    # 逐实例详细表
    print(f"\n{'实例':<14} {'旧合法':>6} {'新合法':>6} {'ΔWait':>10} {'ΔMemory':>10} {'ΔFinish':>10} {'ΔTime':>8}")
    print("-" * 70)

    for d in diffs:
        dw_str = f"{d.delta_wait:+.2f}" if d.old.e_wait is not None else "-"
        dm_str = f"{d.delta_memory:+.2f}" if d.old.e_memory is not None else "-"
        df_str = f"{d.delta_finish:+.2f}" if d.old.e_finish is not None else "-"
        dt_str = f"{d.delta_time:+.3f}" if d.delta_time != 0 else "0.000"

        # 退化标红
        flag = " ⚠" if d.regressed else "  "
        print(f"{d.case_name:<14} {'✓' if d.old.is_legal else '✗':>6} "
              f"{'✓' if d.new.is_legal else '✗':>6} "
              f"{dw_str:>10} {dm_str:>10} {df_str:>10} {dt_str:>8}{flag}")

    # 改进最大 Top 5
    print("\n--- 改进最大的 5 个实例（按 E_wait 减少量）---")
    sorted_improved = sorted(with_wait, key=lambda d: d.delta_wait)
    for d in sorted_improved[:5]:
        print(f"  {d.case_name}: ΔWait={d.delta_wait:+.2f}")

    # 退化最大 Top 5
    print("\n--- 退化最大的 5 个实例（按 E_wait 增加量）---")
    sorted_regressed = sorted(with_wait, key=lambda d: -d.delta_wait)
    for d in sorted_regressed[:5]:
        print(f"  {d.case_name}: ΔWait={d.delta_wait:+.2f}")


def main():
    if len(sys.argv) < 3:
        print(f"用法: {sys.argv[0]} <old_csv_or_dir> <new_csv_or_dir>")
        print(f"示例: {sys.argv[0]} experiments/results/run_20260623_120000 experiments/results/run_20260623_130000")
        print(f"      {sys.argv[0]} experiments/summaries/v0.csv experiments/summaries/v1.csv")
        sys.exit(1)

    old_path = sys.argv[1]
    new_path = sys.argv[2]

    print(f"旧版本: {old_path}")
    print(f"新版本: {new_path}")
    print()

    old_data = auto_read(old_path)
    new_data = auto_read(new_path)

    if not old_data:
        print("[错误] 旧版本无有效数据")
        sys.exit(1)
    if not new_data:
        print("[错误] 新版本无有效数据")
        sys.exit(1)

    print(f"旧版本实例数: {len(old_data)}")
    print(f"新版本实例数: {len(new_data)}")
    print()

    diffs = compare(old_data, new_data)
    print_comparison(diffs)


if __name__ == "__main__":
    main()
