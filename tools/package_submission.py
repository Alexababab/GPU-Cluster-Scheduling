#!/usr/bin/env python3
"""标准化打包脚本 —— 生成符合评测规范的 team24.zip。

用法：
  python3 tools/package_submission.py              # 在项目根目录运行
  python3 tools/package_submission.py --check-only # 只检查不打包

功能：
  1. 收集项目文件，自动排除无关内容
  2. 生成 team24.zip，内部路径全部使用 Linux 正斜杠
  3. 自动解压到临时目录检查结构是否正确
  4. 检查 run.sh / build.sh 是否存在、换行符是否为 LF

为什么写这个脚本：
  测试赛1因为Windows右键压缩导致ZIP内部路径用了反斜杠，
  Linux评测机无法识别，全部100case报ERROR。
  后续所有提交包必须由此脚本生成，不再手动压缩。
"""

import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

TEAM_NAME = "team24"
OUTPUT_ZIP = "team24.zip"

# 需要排除的文件/目录模式
EXCLUDE_PATTERNS = [
    # 版本控制
    ".git/",
    ".gitattributes",
    ".gitignore",
    # 构建产物
    "build/",
    "__pycache__/",
    "*.exe",
    "*.out",
    "*.o",
    # 开发工具与实验
    "tools/",
    "tests/",
    "tmp/",
    "experiments/",
    "research/",
    "docs/",
    # 测试数据（评测系统提供）
    "instances/",
    # 临时文件
    "*.csv",
    "*.zip",
    # 内部文档（README.md 除外，会单独保留）
    "三人任务分工与阶段计划.md",
    "项目框架与三人分工讨论稿.md",
]

# 提交包中必须存在的文件
REQUIRED_FILES = [
    "build.sh",
    "run.sh",
    "CMakeLists.txt",
    "README.md",
]

# 必须存在的目录
REQUIRED_DIRS = [
    "include/",
    "src/",
]


# ---------------------------------------------------------------------------
# 文件收集
# ---------------------------------------------------------------------------

def should_exclude(relpath: str) -> bool:
    """判断文件/目录是否应该排除。

    relpath 使用 / 作为分隔符（已标准化）。
    """
    for pattern in EXCLUDE_PATTERNS:
        # 目录模式：匹配路径前缀或完整目录名
        if pattern.endswith("/"):
            if relpath.startswith(pattern) or ("/" + pattern) in relpath:
                return True
        # 通配符模式
        if fnmatch.fnmatch(os.path.basename(relpath), pattern):
            return True
        # 精确路径前缀匹配
        if relpath == pattern.rstrip("/"):
            return True
    return False


def collect_files(project_root: str) -> List[Tuple[str, str]]:
    """收集需要打包的文件。

    返回 [(磁盘路径, ZIP内路径), ...]，ZIP内路径使用 / 分隔符。

    遍历 project_root 下所有文件，排除匹配 EXCLUDE_PATTERNS 的路径。
    ZIP 内路径前缀为 team24/。
    """
    files: List[Tuple[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        # 计算相对于项目根的路径（用 / 分隔）
        rel_dir = os.path.relpath(dirpath, project_root)
        if rel_dir == ".":
            rel_dir = ""
        else:
            rel_dir = rel_dir.replace("\\", "/") + "/"

        # 跳过被排除的目录（就地修改 dirnames 阻止深入遍历）
        dirnames_to_remove = []
        for d in dirnames:
            check_path = rel_dir + d + "/"
            if should_exclude(check_path):
                dirnames_to_remove.append(d)
        for d in dirnames_to_remove:
            dirnames.remove(d)

        # 跳过自身被排除的目录
        if rel_dir and should_exclude(rel_dir):
            continue

        for f in filenames:
            relpath = rel_dir + f
            if should_exclude(relpath):
                continue

            disk_path = os.path.join(dirpath, f)
            zip_path = f"{TEAM_NAME}/{relpath}"
            # 确保 ZIP 内路径使用正斜杠
            zip_path = zip_path.replace("\\", "/")
            files.append((disk_path, zip_path))

    return files


# ---------------------------------------------------------------------------
# ZIP 打包
# ---------------------------------------------------------------------------

def create_package(project_root: str, output_path: str) -> List[str]:
    """创建 team24.zip。

    返回打包的文件列表（ZIP内路径）。
    """
    files = collect_files(project_root)

    if not files:
        print("❌ 没有找到需要打包的文件，请检查 EXCLUDE_PATTERNS")
        sys.exit(1)

    print(f"收集到 {len(files)} 个文件，正在打包...")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for disk_path, zip_path in files:
            zf.write(disk_path, zip_path)

    # 输出文件大小
    size_kb = os.path.getsize(output_path) / 1024
    print(f"✅ 已生成 {output_path} ({size_kb:.1f} KB)")

    return [zp for _, zp in files]


# ---------------------------------------------------------------------------
# 自动验证
# ---------------------------------------------------------------------------

def validate_package(zip_path: str) -> bool:
    """将生成的 ZIP 解压到临时目录，检查结构是否正确。

    返回 True 表示全部检查通过。
    """
    all_ok = True
    tmp_dir = tempfile.mkdtemp(prefix="pkg_check_")

    try:
        # 解压
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        extracted_root = os.path.join(tmp_dir, TEAM_NAME)
        print(f"\n解压到临时目录: {tmp_dir}")
        print(f"检查目录: {extracted_root}\n")

        # 检查 1：一级目录是否存在
        if not os.path.isdir(extracted_root):
            print(f"❌ 一级目录 {TEAM_NAME}/ 不存在！")
            print(f"   实际内容: {os.listdir(tmp_dir)}")
            # 尝试找实际的一级目录
            items = os.listdir(tmp_dir)
            if items:
                alt_root = os.path.join(tmp_dir, items[0])
                if os.path.isdir(alt_root):
                    print(f"   可能的一级目录: {items[0]}/（应为 {TEAM_NAME}/）")
                    extracted_root = alt_root
            all_ok = False
            # 继续检查实际目录

        # 检查 2：必需文件
        print("─" * 50)
        print("检查必需文件:")
        for fname in REQUIRED_FILES:
            fpath = os.path.join(extracted_root, fname)
            exists = os.path.isfile(fpath)
            status = "✅" if exists else "❌"
            print(f"  {status} {TEAM_NAME}/{fname}")
            if not exists:
                all_ok = False

        # 检查 3：必需目录
        print("\n检查必需目录:")
        for dname in REQUIRED_DIRS:
            dpath = os.path.join(extracted_root, dname.rstrip("/"))
            exists = os.path.isdir(dpath)
            status = "✅" if exists else "❌"
            print(f"  {status} {TEAM_NAME}/{dname}")
            if not exists:
                all_ok = False

        # 检查 4：run.sh 和 build.sh 换行符
        print("\n检查换行符（必须为 LF）:")
        for fname in ["build.sh", "run.sh"]:
            fpath = os.path.join(extracted_root, fname)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, "rb") as f:
                content = f.read()
            if b"\r\n" in content:
                print(f"  ❌ {TEAM_NAME}/{fname}: 包含 Windows CRLF 换行符")
                all_ok = False
            elif b"\r" in content:
                print(f"  ❌ {TEAM_NAME}/{fname}: 包含 CR 字符")
                all_ok = False
            else:
                print(f"  ✅ {TEAM_NAME}/{fname}: LF OK")

        # 检查 5：ZIP 内路径分隔符
        print("\n检查 ZIP 内部路径分隔符:")
        has_backslash = False
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if "\\" in info.filename:
                    print(f"  ❌ 发现反斜杠路径: {info.filename}")
                    has_backslash = True
                    all_ok = False
        if not has_backslash:
            print(f"  ✅ 所有路径使用正斜杠 /")

        # 检查 6：尝试运行 build.sh
        print("\n检查 build.sh 是否可执行:")
        build_script = os.path.join(extracted_root, "build.sh")
        if os.path.isfile(build_script):
            try:
                proc = subprocess.run(
                    ["sh", "build.sh"],
                    cwd=extracted_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60,
                    text=True,
                )
                if proc.returncode == 0:
                    print(f"  ✅ build.sh 执行成功")
                else:
                    print(f"  ❌ build.sh 返回 {proc.returncode}")
                    if proc.stderr:
                        print(f"     stderr: {proc.stderr[:300]}")
                    all_ok = False
            except subprocess.TimeoutExpired:
                print(f"  ❌ build.sh 超时")
                all_ok = False
            except Exception as e:
                print(f"  ❌ build.sh 执行异常: {e}")
                all_ok = False
        else:
            print(f"  ⚠️  build.sh 不存在，跳过构建测试")

        # 总结
        print("\n" + "=" * 50)
        if all_ok:
            print("✅ 所有检查通过，提交包结构正确")
        else:
            print("❌ 存在未通过的检查项，请修复后重新打包")
        print("=" * 50)

        return all_ok

    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    # 确定项目根目录（脚本在 tools/ 下，项目根在上一级）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # 确认在项目根目录
    cmake_path = os.path.join(project_root, "CMakeLists.txt")
    if not os.path.isfile(cmake_path):
        print(f"❌ 无法确认项目根目录: {project_root}")
        print("   请确保脚本位于 tools/ 子目录下，且项目根目录包含 CMakeLists.txt")
        sys.exit(1)

    print(f"项目根目录: {project_root}")
    print(f"队名: {TEAM_NAME}")
    print()

    output_path = os.path.join(project_root, OUTPUT_ZIP)

    # 如果已有旧 ZIP，先删除
    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"已删除旧的 {OUTPUT_ZIP}")

    # 打包
    zip_files = create_package(project_root, output_path)

    # 输出简要文件清单
    print(f"\n打包文件清单（前20个）:")
    for zp in zip_files[:20]:
        print(f"  {zp}")
    if len(zip_files) > 20:
        print(f"  ... 共 {len(zip_files)} 个文件")

    # 验证
    ok = validate_package(output_path)

    if ok:
        print(f"\n🎉 提交包已就绪: {output_path}")
        print("   可以直接提交到评测系统。")
    else:
        print(f"\n⚠️  提交包已生成但存在警告: {output_path}")
        print("   请修复上述问题后重新运行本脚本。")
        sys.exit(1)


if __name__ == "__main__":
    main()
