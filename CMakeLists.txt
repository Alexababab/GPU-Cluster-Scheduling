cmake_minimum_required(VERSION 3.16)

project(gpu_cluster_scheduler LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(scheduler
    src/main.cpp
    src/io.cpp
    src/scheduler.cpp
)

target_include_directories(scheduler PRIVATE include)

if(MSVC)
    target_compile_options(scheduler PRIVATE /W4 /permissive-)
else()
    target_compile_options(scheduler PRIVATE -Wall -Wextra -Wpedantic)
endif()

