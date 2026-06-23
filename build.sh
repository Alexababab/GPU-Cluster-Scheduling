#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
mkdir -p build

CXX="${CXX:-g++}"
if ! command -v "$CXX" >/dev/null 2>&1; then
    if [ -x "/c/msys64/ucrt64/bin/g++.exe" ]; then
        CXX="/c/msys64/ucrt64/bin/g++.exe"
    else
        echo "C++ compiler not found: $CXX" >&2
        exit 127
    fi
fi

"$CXX" -std=c++17 -O2 -Wall -Wextra -Wpedantic \
    -Iinclude \
    src/main.cpp src/io.cpp src/scheduler_config.cpp \
    src/server_state.cpp src/scheduler.cpp \
    -o build/scheduler

"$CXX" -std=c++17 -O2 -Wall -Wextra -Wpedantic \
    -Iinclude \
    src/validate_main.cpp src/io.cpp src/validator.cpp src/metrics.cpp \
    -o build/validator
