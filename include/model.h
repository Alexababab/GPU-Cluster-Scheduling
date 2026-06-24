#pragma once

#include <vector>

struct Server {
    int id = 0;
    int gpu_count = 0;
    int gpu_memory = 0;
    int cpu_cores = 0;
    int memory = 0;
};

struct Task {
    int id = 0;
    long long release_time = 0;
    long long duration = 0;
    int min_gpu = 0;
    int total_gpu_memory = 0;
    int cpu_cores = 0;
    int memory = 0;
    int weight = 0;
};

struct Instance {
    std::vector<Server> servers;
    std::vector<Task> tasks;
};

struct Assignment {
    int task_id = 0;
    int server_id = 0;
    long long start_time = 0;
    int gpu_count = 0;
    long long finish_time = 0;
};

struct RunningTask {
    int task_id = 0;
    int server_id = 0;
    long long finish_time = 0;
    int gpu_count = 0;
    int cpu_cores = 0;
    int memory = 0;
};
