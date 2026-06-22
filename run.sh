#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ -x "./build/scheduler" ]; then
    exec ./build/scheduler
fi

if [ -x "./build/scheduler.exe" ]; then
    exec ./build/scheduler.exe
fi

echo "scheduler executable not found; run sh build.sh first" >&2
exit 1
