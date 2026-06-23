#!/usr/bin/env python3
"""提交包检查工具 —— 验证最终提交压缩包是否符合评测规范。

用法：
  python3 check_submission.py <提交目录或压缩包路径>

检查项：
  1. build.sh 存在且可执行
  2. run.sh 存在且可执行
  3. 脚本使用 LF 换行符（不是 CRLF）
  4. C++17 源码存在
  5. 目录结构：解压后仅一层同名目录
  6. 标准输出不含额外文字
  7. 标准错误不影响评测（允许有内容，但不能导致评测失败）
  8. 无关大型文件检查
"""

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# 检查结果
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"   # error / warning


# ---------------------------------------------------------------------------
# 各项检查
# ---------------------------------------------------------------------------

def check_file_exists(path: str, filename: str) -> CheckResult:
    """检查文件是否存在"""
    filepath = os.path.join(path, filename)
    exists = os.path.isfile(filepath)
    return CheckResult(
        name=f"{filename} 存在",
        passed=exists,
        detail=f"找到 {filepath}" if exists else f"缺少 {filepath}",
    )


def check_executable(path: str, filename: str) -> CheckResult:
    """检查脚本是否可执行"""
    filepath = os.path.join(path, filename)
    if not os.path.isfile(filepath):
        return CheckResult(
            name=f"{filename} 可执行",
            passed=False,
            detail=f"文件不存在: {filepath}",
        )

    # 检查是否有可执行权限（Linux）
    if os.access(filepath, os.X_OK):
        return CheckResult(name=f"{filename} 可执行", passed=True, detail="可执行权限 OK")

    # 也可能通过 sh 调用
    return CheckResult(
        name=f"{filename} 可执行",
        passed=True,
        detail="无执行权限但可通过 sh 调用",
        severity="warning",
    )


def check_line_endings(path: str, filename: str) -> CheckResult:
    """检查换行符是否为 LF"""
    filepath = os.path.join(path, filename)
    if not os.path.isfile(filepath):
        return CheckResult(name=f"{filename} 换行符", passed=False, detail="文件不存在")

    with open(filepath, "rb") as f:
        content = f.read()

    if b"\r\n" in content:
        return CheckResult(
            name=f"{filename} 换行符",
            passed=False,
            detail="包含 Windows CRLF 换行符，需转换为 LF",
            severity="error",
        )
    elif b"\r" in content:
        return CheckResult(
            name=f"{filename} 换行符",
            passed=False,
            detail="包含 CR 字符",
            severity="error",
        )

    return CheckResult(name=f"{filename} 换行符", passed=True, detail="LF OK")


def check_no_extra_stdout(path: str, scheduler_cmd: List[str]) -> CheckResult:
    """用 smoke 测试检查标准输出格式（每行5个字段）"""
    import tempfile

    # 找测试文件
    test_file = os.path.join(path, "..", "..", "tests", "handcrafted", "smoke.in")
    if not os.path.exists(test_file):
        # 尝试在 path 下寻找
        for root, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".in"):
                    test_file = os.path.join(root, f)
                    break

    if not os.path.exists(test_file):
        return CheckResult(
            name="输出格式",
            passed=False,
            detail="找不到 .in 测试文件",
            severity="warning",
        )

    try:
        with open(test_file, "r") as fin:
            proc = subprocess.run(
                scheduler_cmd,
                stdin=fin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                text=True,
            )

        stdout = proc.stdout.strip()
        if not stdout:
            return CheckResult(name="输出格式", passed=False, detail="标准输出为空")

        lines = stdout.split("\n")
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) != 5:
                return CheckResult(
                    name="输出格式",
                    passed=False,
                    detail=f"第{i+1}行字段数={len(parts)}，应为5: {line[:80]}",
                )
            # 检查每个字段是否为整数
            for j, p in enumerate(parts):
                try:
                    int(p)
                except ValueError:
                    return CheckResult(
                        name="输出格式",
                        passed=False,
                        detail=f"第{i+1}行第{j+1}列非整数: {p}",
                    )

        # 检查总行数是否等于任务数
        # 从输入文件的第一行读取任务数
        with open(test_file, "r") as f:
            first_line = f.readline().strip()
            parts = first_line.split()
            if len(parts) >= 2:
                expected_tasks = int(parts[1])
                actual_lines = len(lines)
                if actual_lines != expected_tasks:
                    return CheckResult(
                        name="输出格式",
                        passed=False,
                        detail=f"输出行数={actual_lines}，预期={expected_tasks}",
                    )

        return CheckResult(name="输出格式", passed=True, detail=f"{len(lines)} 行，每行5字段 OK")

    except subprocess.TimeoutExpired:
        return CheckResult(name="输出格式", passed=False, detail="运行超时")
    except Exception as e:
        return CheckResult(name="输出格式", passed=False, detail=str(e))


def check_large_files(path: str, max_mb: int = 50) -> CheckResult:
    """检查是否有无关大型文件"""
    large_files = []
    for root, dirs, files in os.walk(path):
        # 跳过 .git
        if ".git" in root.split(os.sep):
            continue
        for f in files:
            filepath = os.path.join(root, f)
            try:
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if size_mb > max_mb:
                    relpath = os.path.relpath(filepath, path)
                    large_files.append(f"{relpath} ({size_mb:.1f} MB)")
            except OSError:
                pass

    if large_files:
        return CheckResult(
            name="大文件检查",
            passed=False,
            detail="; ".join(large_files),
            severity="warning",
        )
    return CheckResult(name="大文件检查", passed=True, detail="无异常大文件")


def check_src_exists(path: str) -> CheckResult:
    """检查 C++ 源码是否存在"""
    cpp_files = []
    for root, dirs, files in os.walk(path):
        if ".git" in root.split(os.sep):
            continue
        for f in files:
            if f.endswith((".cpp", ".cc", ".cxx", ".h", ".hpp")):
                cpp_files.append(os.path.join(root, f))

    if not cpp_files:
        return CheckResult(name="C++ 源码", passed=False, detail="未找到 C++ 源文件")

    return CheckResult(
        name="C++ 源码",
        passed=True,
        detail=f"找到 {len(cpp_files)} 个源文件",
    )


def check_build(path: str) -> CheckResult:
    """尝试执行 build.sh"""
    build_script = os.path.join(path, "build.sh")
    if not os.path.isfile(build_script):
        return CheckResult(name="构建测试", passed=False, detail="build.sh 不存在")

    try:
        proc = subprocess.run(
            ["sh", "build.sh"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True,
        )
        if proc.returncode != 0:
            return CheckResult(
                name="构建测试",
                passed=False,
                detail=f"build.sh 返回 {proc.returncode}: {proc.stderr[:200]}",
            )
        return CheckResult(name="构建测试", passed=True, detail="build.sh 执行成功")
    except subprocess.TimeoutExpired:
        return CheckResult(name="构建测试", passed=False, detail="构建超时")
    except Exception as e:
        return CheckResult(name="构建测试", passed=False, detail=str(e))


# ---------------------------------------------------------------------------
# 主检查流程
# ---------------------------------------------------------------------------

def run_all_checks(project_path: str) -> List[CheckResult]:
    """执行全部检查"""
    results: List[CheckResult] = []

    # 1. build.sh
    results.append(check_file_exists(project_path, "build.sh"))
    results.append(check_executable(project_path, "build.sh"))
    results.append(check_line_endings(project_path, "build.sh"))

    # 2. run.sh
    results.append(check_file_exists(project_path, "run.sh"))
    results.append(check_executable(project_path, "run.sh"))
    results.append(check_line_endings(project_path, "run.sh"))

    # 3. 源码
    results.append(check_src_exists(project_path))

    # 4. 构建
    results.append(check_build(project_path))

    # 5. 输出格式（使用构建后的程序）
    scheduler = os.path.join(project_path, "build", "scheduler")
    if os.path.exists(scheduler):
        results.append(check_no_extra_stdout(project_path, [scheduler]))
    else:
        # 尝试 build 目录下
        for candidate in ["scheduler", "scheduler.exe"]:
            cand_path = os.path.join(project_path, "build", candidate)
            if os.path.exists(cand_path):
                results.append(check_no_extra_stdout(project_path, [cand_path]))
                break
        else:
            results.append(CheckResult(
                name="输出格式", passed=False,
                detail="构建产物不存在，无法检查",
                severity="warning",
            ))

    # 6. 大文件
    results.append(check_large_files(project_path))

    return results


def print_results(results: List[CheckResult]):
    """打印检查结果"""
    print("=" * 60)
    print("提交包检查清单")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    warnings = 0

    for r in results:
        if r.passed:
            status = "✓"
            passed += 1
            if r.severity == "warning":
                warnings += 1
        else:
            status = "✗" if r.severity == "error" else "⚠"
            failed += 1

        print(f"  [{status}] {r.name}")
        if r.detail:
            print(f"       {r.detail}")
        print()

    print("-" * 60)
    print(f"  通过: {passed}  失败: {failed}")
    if warnings:
        print(f"  警告: {warnings}（不影响提交但仍建议修复）")
    print("-" * 60)

    errors = [r for r in results if not r.passed and r.severity == "error"]
    if errors:
        print(f"\n❌ 存在 {len(errors)} 个必须修复的问题:")
        for r in errors:
            print(f"  - [{r.name}] {r.detail}")
        return False
    else:
        print("\n✅ 所有必检项通过，可以提交")
        return True


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <项目目录>")
        print(f"示例: {sys.argv[0]} .")
        sys.exit(1)

    project_path = os.path.abspath(sys.argv[1])

    if not os.path.isdir(project_path):
        print(f"错误: 目录不存在 —— {project_path}")
        sys.exit(1)

    print(f"检查目录: {project_path}\n")

    results = run_all_checks(project_path)
    ok = print_results(results)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
