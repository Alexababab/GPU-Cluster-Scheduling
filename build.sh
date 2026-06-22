#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
mkdir -p build
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
    -Iinclude \
    src/main.cpp src/io.cpp src/server_state.cpp src/scheduler.cpp \
    -o build/scheduler
