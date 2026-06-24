#!/usr/bin/env python3
"""测试赛记录工具 —— 保存提交版本、Git tag、本地指标、排名成绩。

用法：
    # 比赛前：打 tag 并记录使用的配置
    python3 tools/match_record.py tag <比赛名称> --config scheduler_config.txt

    # 比赛后：填写排名和成绩
    python3 tools/match_record.py score <比赛名称> --rank 3 --score 95.5

    # 列出所有比赛记录
    python3 tools/match_record.py list

    # 查看某场比赛详情
    python3 tools/match_record.py show <比赛名称>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 项目根目录
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATCHES_DIR = PROJECT_ROOT / "experiments" / "matches"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class MatchRecord:
    name: str                          # 比赛名称，如 test_round_1
    tag: str                           # git tag
    commit: str                        # git commit hash
    timestamp: str                     # ISO 时间戳
    config: dict[str, str] = field(default_factory=dict)
    config_name: str = ""              # 使用的预设名称（v0/v1a/v1b/custom）
    instances_dir: str = "instances/"
    total_instances: int = 100

    # 赛后填写
    rank: int = 0                      # 排名
    score: float = 0.0                 # 得分
    public_leaderboard_url: str = ""   # 排行榜链接
    notes: str = ""                    # 备注


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def ensure_matches_dir() -> Path:
    MATCHES_DIR.mkdir(parents=True, exist_ok=True)
    return MATCHES_DIR


def match_path(name: str) -> Path:
    return ensure_matches_dir() / name


def record_path(name: str) -> Path:
    return match_path(name) / "match_info.json"


def load_record(name: str) -> MatchRecord | None:
    path = record_path(name)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return MatchRecord(**data)


def save_record(record: MatchRecord) -> None:
    mp = match_path(record.name)
    mp.mkdir(parents=True, exist_ok=True)
    path = mp / "match_info.json"
    path.write_text(
        json.dumps(asdict(record), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def git(command: list[str]) -> str:
    """在项目根目录执行 git 命令，返回 stdout。"""
    result = subprocess.run(
        ["git"] + command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={"GIT_SSL_NO_VERIFY": "1", **__import__("os").environ},
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(command)} 失败: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_config_file(path: Path) -> dict[str, str]:
    """解析 scheduler_config.txt 为字典。"""
    params: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            params[key.strip()] = value.strip()
    return params


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_tag(args: argparse.Namespace) -> int:
    """打比赛标签。"""
    match_name: str = args.match_name

    # 检查是否已存在
    if load_record(match_name):
        print(f"比赛 '{match_name}' 已存在，使用 'show' 查看或 'score' 更新成绩")
        return 1

    # 获取当前 git 状态
    try:
        commit = git(["rev-parse", "HEAD"])
        short_commit = commit[:8]
    except RuntimeError as e:
        print(f"Git 错误: {e}", file=sys.stderr)
        return 1

    # 检查是否有未提交的改动
    try:
        status = git(["status", "--porcelain"])
        if status:
            print("⚠️  警告: 工作区有未提交的改动，建议先提交再打 tag")
            print(status)
    except RuntimeError:
        pass

    # 生成 tag 名称
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_name = f"match/{match_name}_{timestamp}"

    # 创建 tag
    try:
        git(["tag", "-a", tag_name, "-m", f"测试赛: {match_name}"])
        print(f"Git tag 已创建: {tag_name}")
    except RuntimeError as e:
        print(f"创建 tag 失败: {e}", file=sys.stderr)
        return 1

    # 解析配置文件
    config: dict[str, str] = {}
    config_name = ""
    if args.config:
        config_path = Path(args.config).resolve()
        if config_path.is_file():
            config = parse_config_file(config_path)
            # 确保目录存在再复制配置文件
            import shutil
            mp = match_path(match_name)
            mp.mkdir(parents=True, exist_ok=True)
            shutil.copy(config_path, mp / "config.txt")
            print(f"配置文件已保存: {mp / 'config.txt'}")
        else:
            print(f"配置文件不存在: {config_path}", file=sys.stderr)
            return 1

    # 获取 config_name（从环境变量或从配置推断）
    if args.config_name:
        config_name = args.config_name
    elif config:
        config_name = "custom"
    else:
        config_name = "v1b"

    # 创建记录
    record = MatchRecord(
        name=match_name,
        tag=tag_name,
        commit=commit,
        timestamp=datetime.now().isoformat(),
        config=config,
        config_name=config_name,
        instances_dir=str(args.instances_dir) if args.instances_dir else "instances/",
        total_instances=args.total_instances,
    )
    save_record(record)

    print(f"\n✅ 比赛记录已创建: {match_name}")
    print(f"   Tag:     {tag_name}")
    print(f"   Commit:  {short_commit}")
    print(f"   Config:  {config_name}")
    print(f"   配置参数: {len(config)} 项")
    print(f"\n比赛结束后运行:")
    print(f"  python3 tools/match_record.py score {match_name} --rank <排名> --score <得分>")

    return 0


def cmd_score(args: argparse.Namespace) -> int:
    """填写比赛成绩。"""
    match_name: str = args.match_name
    record = load_record(match_name)
    if record is None:
        print(f"比赛 '{match_name}' 不存在", file=sys.stderr)
        return 1

    if args.rank is not None:
        record.rank = args.rank
    if args.score is not None:
        record.score = args.score
    if args.url:
        record.public_leaderboard_url = args.url
    if args.notes:
        record.notes = args.notes

    save_record(record)

    print(f"✅ 比赛成绩已更新: {match_name}")
    if record.rank:
        print(f"   排名: {record.rank}")
    if record.score:
        print(f"   得分: {record.score}")
    if record.public_leaderboard_url:
        print(f"   链接: {record.public_leaderboard_url}")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出所有比赛记录。"""
    ensure_matches_dir()
    matches = sorted(
        [d for d in MATCHES_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    if not matches:
        print("暂无比赛记录")
        return 0

    print(f"{'名称':<30} {'Tag':<50} {'排名':<6} {'得分':<10}")
    print("-" * 96)
    for mp in matches:
        record = load_record(mp.name)
        if record is None:
            continue
        tag_short = record.tag[-50:] if len(record.tag) > 50 else record.tag
        rank_str = str(record.rank) if record.rank else "-"
        score_str = f"{record.score:.2f}" if record.score else "-"
        print(f"{record.name:<30} {tag_short:<50} {rank_str:<6} {score_str:<10}")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """显示比赛详情。"""
    match_name: str = args.match_name
    record = load_record(match_name)
    if record is None:
        print(f"比赛 '{match_name}' 不存在", file=sys.stderr)
        return 1

    print(f"比赛名称: {record.name}")
    print(f"Git Tag:  {record.tag}")
    print(f"Commit:   {record.commit}")
    print(f"时间:     {record.timestamp}")
    print(f"配置名称: {record.config_name}")
    print(f"实例目录: {record.instances_dir}")
    print(f"实例数量: {record.total_instances}")
    print(f"排名:     {record.rank or '未填写'}")
    print(f"得分:     {record.score or '未填写'}")
    if record.public_leaderboard_url:
        print(f"排行榜:   {record.public_leaderboard_url}")
    if record.notes:
        print(f"备注:     {record.notes}")

    if record.config:
        print(f"\n配置参数 ({len(record.config)} 项):")
        for key, value in record.config.items():
            print(f"  {key} = {value}")

    # 检查是否有保存的结果文件
    result_files = sorted((match_path(match_name)).glob("*.csv"))
    if result_files:
        print(f"\n结果文件:")
        for rf in result_files:
            size_kb = rf.stat().st_size / 1024
            print(f"  {rf.name} ({size_kb:.1f} KB)")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="测试赛记录工具 —— 保存版本、指标、成绩"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # tag
    tag_parser = sub.add_parser("tag", help="打比赛标签")
    tag_parser.add_argument("match_name", help="比赛名称，如 test_round_1")
    tag_parser.add_argument("--config", type=Path, default=None,
                            help="scheduler_config.txt 路径")
    tag_parser.add_argument("--config-name", default="",
                            help="预设名称（v0/v1a/v1b/custom）")
    tag_parser.add_argument("--instances-dir", default="instances/",
                            help="实例目录")
    tag_parser.add_argument("--total-instances", type=int, default=100,
                            help="实例总数")

    # score
    score_parser = sub.add_parser("score", help="填写比赛成绩")
    score_parser.add_argument("match_name", help="比赛名称")
    score_parser.add_argument("--rank", type=int, default=None, help="排名")
    score_parser.add_argument("--score", type=float, default=None, help="得分")
    score_parser.add_argument("--url", default="", help="排行榜链接")
    score_parser.add_argument("--notes", default="", help="备注")

    # list
    sub.add_parser("list", help="列出所有比赛记录")

    # show
    show_parser = sub.add_parser("show", help="查看比赛详情")
    show_parser.add_argument("match_name", help="比赛名称")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.command == "tag":
        return cmd_tag(args)
    elif args.command == "score":
        return cmd_score(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    else:
        print("请指定子命令: tag / score / list / show", file=sys.stderr)
        print("用法: python3 tools/match_record.py tag <名称> --config scheduler_config.txt", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
