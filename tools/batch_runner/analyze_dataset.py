#!/usr/bin/env python3
"""数据集分析工具 —— 统计 100 个公开实例的特征并分类。

用法：
  python3 analyze_dataset.py <instances_dir>

输出：
  - 每个实例的详细统计（控制台表格）
  - dataset_profile.csv（可导入 Excel）
  - 四档分类结果
"""

import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# 数据模型（与 C++ model.h 对齐）
# ---------------------------------------------------------------------------

@dataclass
class Server:
    id: int
    gpu_count: int
    gpu_memory: int   # 单卡显存
    cpu_cores: int
    memory: int        # 内存容量


@dataclass
class Task:
    id: int
    release_time: int   # 提交时间
    duration: int        # 运行时长
    min_gpu: int         # 最低 GPU 数量
    total_gpu_memory: int  # 总显存需求
    cpu_cores: int
    memory: int
    weight: int          # 优先级权重


# ---------------------------------------------------------------------------
# 每个实例的统计结果
# ---------------------------------------------------------------------------

@dataclass
class InstanceProfile:
    """单个实例的完整画像"""
    filename: str
    server_count: int
    task_count: int

    # 任务提交时间
    release_min: int = 0
    release_max: int = 0

    # 运行时长
    duration_min: int = 0
    duration_max: int = 0
    duration_avg: float = 0.0
    duration_median: float = 0.0

    # 优先级权重
    weight_min: int = 0
    weight_max: int = 0
    weight_avg: float = 0.0

    # GPU 需求
    gpu_min: int = 0
    gpu_max: int = 0
    gpu_avg: float = 0.0
    multi_gpu_ratio: float = 0.0   # 需要多 GPU 的任务比例

    # 显存 / CPU / 内存需求
    gpu_mem_min: int = 0
    gpu_mem_max: int = 0
    cpu_min: int = 0
    cpu_max: int = 0
    mem_min: int = 0
    mem_max: int = 0

    # 可行服务器数量
    feasible_min: int = 0
    feasible_max: int = 0
    feasible_avg: float = 0.0
    scarce_task_count: int = 0   # 可行服务器 ≤ 2 的任务数

    # 服务器异构程度（GPU 数量标准差）
    server_gpu_std: float = 0.0

    # 分类
    difficulty: str = ""


# ---------------------------------------------------------------------------
# 输入解析（与 C++ io.cpp 对齐）
# ---------------------------------------------------------------------------

def ceil_div(a: int, b: int) -> int:
    """整数除法向上取整"""
    return (a + b - 1) // b


def parse_instance(filepath: str) -> Tuple[List[Server], List[Task]]:
    """读取一个 .in 文件，返回服务器列表和任务列表"""
    with open(filepath, "r") as f:
        lines = f.readlines()

    # 过滤空行和注释行
    tokens = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            tokens.extend(line.split())

    idx = 0
    if len(tokens) < 2:
        raise ValueError(f"{filepath}: 输入格式错误，token 不足")

    server_count = int(tokens[idx]); idx += 1
    task_count = int(tokens[idx]); idx += 1

    servers = []
    for i in range(server_count):
        s = Server(
            id=i + 1,
            gpu_count=int(tokens[idx]),
            gpu_memory=int(tokens[idx + 1]),
            cpu_cores=int(tokens[idx + 2]),
            memory=int(tokens[idx + 3]),
        )
        idx += 4
        servers.append(s)

    tasks = []
    for i in range(task_count):
        t = Task(
            id=i + 1,
            release_time=int(tokens[idx]),
            duration=int(tokens[idx + 1]),
            min_gpu=int(tokens[idx + 2]),
            total_gpu_memory=int(tokens[idx + 3]),
            cpu_cores=int(tokens[idx + 4]),
            memory=int(tokens[idx + 5]),
            weight=int(tokens[idx + 6]),
        )
        idx += 7
        tasks.append(t)

    return servers, tasks


# ---------------------------------------------------------------------------
# 统计分析
# ---------------------------------------------------------------------------

def compute_feasible_servers(task: Task, servers: List[Server]) -> int:
    """计算某个任务在多少台服务器上可行"""
    count = 0
    for s in servers:
        gpu_for_mem = ceil_div(task.total_gpu_memory, s.gpu_memory) if s.gpu_memory > 0 else 999999
        required_gpu = max(task.min_gpu, gpu_for_mem)
        if (required_gpu <= s.gpu_count and
            task.cpu_cores <= s.cpu_cores and
            task.memory <= s.memory):
            count += 1
    return count


def median(values: List[int]) -> float:
    """计算中位数"""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n % 2 == 1:
        return float(sorted_v[n // 2])
    return (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0


def std_dev(values: List[float]) -> float:
    """计算标准差"""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def profile_instance(filename: str, servers: List[Server], tasks: List[Task]) -> InstanceProfile:
    """对单个实例生成完整画像"""
    p = InstanceProfile(
        filename=filename,
        server_count=len(servers),
        task_count=len(tasks),
    )

    if not tasks:
        return p

    # 提交时间
    releases = [t.release_time for t in tasks]
    p.release_min = min(releases)
    p.release_max = max(releases)

    # 运行时长
    durations = [t.duration for t in tasks]
    p.duration_min = min(durations)
    p.duration_max = max(durations)
    p.duration_avg = sum(durations) / len(durations)
    p.duration_median = median(durations)

    # 权重
    weights = [t.weight for t in tasks]
    p.weight_min = min(weights)
    p.weight_max = max(weights)
    p.weight_avg = sum(weights) / len(weights)

    # GPU 需求
    gpus = [t.min_gpu for t in tasks]
    p.gpu_min = min(gpus)
    p.gpu_max = max(gpus)
    p.gpu_avg = sum(gpus) / len(gpus)
    p.multi_gpu_ratio = sum(1 for g in gpus if g > 1) / len(gpus)

    # 显存 / CPU / 内存
    p.gpu_mem_min = min(t.total_gpu_memory for t in tasks)
    p.gpu_mem_max = max(t.total_gpu_memory for t in tasks)
    p.cpu_min = min(t.cpu_cores for t in tasks)
    p.cpu_max = max(t.cpu_cores for t in tasks)
    p.mem_min = min(t.memory for t in tasks)
    p.mem_max = max(t.memory for t in tasks)

    # 可行服务器
    feasible_counts = [compute_feasible_servers(t, servers) for t in tasks]
    p.feasible_min = min(feasible_counts)
    p.feasible_max = max(feasible_counts)
    p.feasible_avg = sum(feasible_counts) / len(feasible_counts)
    p.scarce_task_count = sum(1 for fc in feasible_counts if fc <= 2)

    # 服务器 GPU 异构程度
    p.server_gpu_std = std_dev([float(s.gpu_count) for s in servers])

    return p


# ---------------------------------------------------------------------------
# 四档分类
# ---------------------------------------------------------------------------

def classify_difficulty(p: InstanceProfile) -> str:
    """根据实例特征分为四档：简单 / 中等 / 困难 / 极端"""
    # 综合评分 = 任务数 + 服务器数 + 稀缺任务比例 + 多GPU任务比例
    score = 0.0

    # 任务数量（越大越难）
    if p.task_count <= 20:
        score += 0
    elif p.task_count <= 100:
        score += 1
    elif p.task_count <= 500:
        score += 2
    else:
        score += 3

    # 稀缺任务比例
    scarce_ratio = p.scarce_task_count / max(p.task_count, 1)
    if scarce_ratio <= 0.1:
        score += 0
    elif scarce_ratio <= 0.3:
        score += 1
    elif scarce_ratio <= 0.5:
        score += 2
    else:
        score += 3

    # 多 GPU 任务比例
    if p.multi_gpu_ratio <= 0.2:
        score += 0
    elif p.multi_gpu_ratio <= 0.5:
        score += 1
    elif p.multi_gpu_ratio <= 0.8:
        score += 2
    else:
        score += 3

    # 服务器异构程度
    if p.server_gpu_std <= 1.0:
        score += 0
    elif p.server_gpu_std <= 2.0:
        score += 1
    else:
        score += 2

    if score <= 2:
        return "简单"
    elif score <= 4:
        return "中等"
    elif score <= 7:
        return "困难"
    else:
        return "极端"


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------

def print_instance_table(profiles: List[InstanceProfile]):
    """打印逐实例详细表格"""
    header = (
        f"{'文件':<14} {'服务器':>5} {'任务':>6} "
        f"{'提交范围':>16} {'时长(均/最)':>16} {'权重均':>6} "
        f"{'GPU均':>5} {'多GPU%':>7} {'稀缺':>4} "
        f"{'可行(min/max)':>16} {'分类':>4}"
    )
    print(header)
    print("-" * len(header))

    for p in profiles:
        release_range = f"{p.release_min}-{p.release_max}"
        dur_info = f"{p.duration_avg:.0f}/{p.duration_max}"
        print(
            f"{p.filename:<14} {p.server_count:>5} {p.task_count:>6} "
            f"{release_range:>16} {dur_info:>16} {p.weight_avg:>6.1f} "
            f"{p.gpu_avg:>5.1f} {p.multi_gpu_ratio*100:>6.1f}% {p.scarce_task_count:>4} "
            f"({p.feasible_min}/{p.feasible_max}):>16 {p.difficulty:>4}"
        )


def print_summary_by_difficulty(profiles: List[InstanceProfile]):
    """按四档汇总"""
    groups = defaultdict(list)
    for p in profiles:
        groups[p.difficulty].append(p)

    print("\n========== 四档汇总 ==========\n")
    print(f"{'分类':<6} {'实例数':>6} {'平均服务器':>8} {'平均任务':>8} {'平均稀缺%':>9} {'平均多GPU%':>10}")
    print("-" * 55)

    for diff in ["简单", "中等", "困难", "极端"]:
        group = groups[diff]
        if not group:
            continue
        n = len(group)
        avg_srv = sum(p.server_count for p in group) / n
        avg_task = sum(p.task_count for p in group) / n
        avg_scarce = sum(p.scarce_task_count / max(p.task_count, 1) for p in group) / n * 100
        avg_multi = sum(p.multi_gpu_ratio for p in group) / n * 100
        print(f"{diff:<6} {n:>6} {avg_srv:>8.1f} {avg_task:>8.1f} {avg_scarce:>8.1f}% {avg_multi:>9.1f}%")


def export_csv(profiles: List[InstanceProfile], output_path: str):
    """导出 CSV 文件"""
    import csv
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "文件名", "服务器数", "任务数",
            "提交时间_min", "提交时间_max",
            "时长_min", "时长_max", "时长_avg", "时长_median",
            "权重_min", "权重_max", "权重_avg",
            "GPU_min", "GPU_max", "GPU_avg", "多GPU任务比例",
            "显存_min", "显存_max",
            "CPU_min", "CPU_max",
            "内存_min", "内存_max",
            "可行服务器_min", "可行服务器_max", "可行服务器_avg",
            "稀缺任务数", "服务器GPU标准差",
            "分类",
        ])
        for p in profiles:
            writer.writerow([
                p.filename, p.server_count, p.task_count,
                p.release_min, p.release_max,
                p.duration_min, p.duration_max, f"{p.duration_avg:.2f}", f"{p.duration_median:.1f}",
                p.weight_min, p.weight_max, f"{p.weight_avg:.2f}",
                p.gpu_min, p.gpu_max, f"{p.gpu_avg:.2f}", f"{p.multi_gpu_ratio:.4f}",
                p.gpu_mem_min, p.gpu_mem_max,
                p.cpu_min, p.cpu_max,
                p.mem_min, p.mem_max,
                p.feasible_min, p.feasible_max, f"{p.feasible_avg:.2f}",
                p.scarce_task_count, f"{p.server_gpu_std:.2f}",
                p.difficulty,
            ])
    print(f"\nCSV 已导出: {output_path}")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <instances_dir>")
        sys.exit(1)

    instances_dir = sys.argv[1]
    if not os.path.isdir(instances_dir):
        print(f"错误: 目录不存在 —— {instances_dir}")
        sys.exit(1)

    # 收集所有 .in 文件
    in_files = sorted(
        os.path.join(instances_dir, f)
        for f in os.listdir(instances_dir)
        if f.endswith(".in")
    )

    if not in_files:
        print(f"警告: {instances_dir} 下没有 .in 文件")
        sys.exit(1)

    print(f"找到 {len(in_files)} 个实例\n")

    # 逐实例分析
    profiles: List[InstanceProfile] = []
    for filepath in in_files:
        try:
            servers, tasks = parse_instance(filepath)
            p = profile_instance(os.path.basename(filepath), servers, tasks)
            p.difficulty = classify_difficulty(p)
            profiles.append(p)
        except Exception as e:
            print(f"[跳过] {os.path.basename(filepath)}: {e}")

    # 输出
    print_instance_table(profiles)
    print_summary_by_difficulty(profiles)

    # 导出 CSV
    csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "experiments", "summaries", "dataset_profile.csv")
    export_csv(profiles, csv_path)

    # 输出稀缺任务实例列表
    print("\n========== 稀缺任务实例 ==========\n")
    for p in profiles:
        if p.scarce_task_count > 0:
            print(f"  {p.filename}: {p.scarce_task_count}/{p.task_count} 个稀缺任务（可行服务器≤2）")

    print("\n分析完成。")


if __name__ == "__main__":
    main()
