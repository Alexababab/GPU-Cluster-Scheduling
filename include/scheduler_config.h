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
    double w_residual_imbalance = 0.0;
};

struct IsolationScoreConfig {
    bool enabled = false;
    int large_task_gpu_threshold = 4;
    int high_capacity_gpu_threshold = 8;
    double w_high_capacity_reserve = 0.0;
    double w_class_mismatch = 0.0;
    double w_same_class_affinity = 0.0;
};

struct MemoryAwareScoreConfig {
    bool enabled = false;
    double w_duration_memory_waste = 0.0;
    double duration_log_scale = 0.0;
};

struct SchedulerConfig {
    std::string name = "v1b_filter_score";
    TaskScoreConfig task_score;
    ServerScoreConfig server_score;
    IsolationScoreConfig isolation_score;
    MemoryAwareScoreConfig memory_aware_score;
};

SchedulerConfig scheduler_config_from_name(const std::string& name);

SchedulerConfig scheduler_config_from_file(const std::string& path);
