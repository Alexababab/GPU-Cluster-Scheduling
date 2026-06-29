#!/usr/bin/env sh
# ============================================================
# submit.sh —— 一键构建 + 打包，生成提交就绪的 team24.zip
#
# 用法：
#   sh submit.sh              # 完整流程：构建 + 打包
#   sh submit.sh --no-build   # 跳过构建，仅打包
#
# 为什么需要这个脚本：
#   测试赛1 因为手动压缩导致 ZIP 路径用反斜杠，全部 case ERROR。
#   此后所有提交包必须走标准化流程，不允许手动压缩。
# ============================================================
set -eu

cd "$(dirname "$0")"

echo "=========================================="
echo "  team24 提交包生成器"
echo "=========================================="
echo ""

# ---- 构建 ----
if [ "${1:-}" != "--no-build" ]; then
    echo "[1/2] 构建项目..."
    sh build.sh
    echo ""
else
    echo "[1/2] 跳过构建 (--no-build)"
    echo ""
fi

# ---- 打包 ----
echo "[2/2] 生成提交包..."
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python 3 not found" >&2
    exit 127
fi

SUBMISSION_CONFIG="${SUBMISSION_CONFIG:-v1d}" \
    "$PYTHON" tools/package_submission.py

echo ""
echo "=========================================="
echo "  提交包 team24.zip 已就绪"
echo "  可直接上传到评测系统"
echo "=========================================="
