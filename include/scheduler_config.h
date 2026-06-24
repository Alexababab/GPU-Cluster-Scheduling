#pragma once

#include <string>

enum class ServerSelectionMode {
    V0BestFit,
    WeightedScore,
};

struct TaskScoreConfig {
    bool enabled = true;
    double w_priority = 2.0;
    double w_wait = 0.01;
    double w_scarcity = 40.0;
    double w_area = 0.20;
    double w_short_job = 4.0;
};

struct ServerScoreConfig {
    ServerSelectionMode mode = ServerSelectionMode::WeightedScore;
    double w_gpu_fragment = 4.0;
    double w_gpu_memory_fragment = 2.0;
    double w_cpu_fragment = 1.0;
    double w_memory_fragment = 1.0;
};

struct SchedulerConfig {
    std::string name = "v1b_filter_score";
    TaskScoreConfig task_score;
    ServerScoreConfig server_score;
};

SchedulerConfig scheduler_config_from_name(const std::string& name);

SchedulerConfig scheduler_config_from_file(const std::string& path);

