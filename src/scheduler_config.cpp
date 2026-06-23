#include "scheduler_config.h"

#include <stdexcept>

SchedulerConfig scheduler_config_from_name(const std::string& name) {
    if (name == "v0" || name == "v0_baseline") {
        SchedulerConfig config;
        config.name = "v0_baseline";
        config.task_score.enabled = false;
        config.server_score.mode = ServerSelectionMode::V0BestFit;
        return config;
    }

    if (name == "v1a" || name == "v1a_task_ordering") {
        SchedulerConfig config;
        config.name = "v1a_task_ordering";
        config.server_score.mode = ServerSelectionMode::V0BestFit;
        return config;
    }

    if (name == "v1b" || name == "v1b_filter_score" || name.empty()) {
        return SchedulerConfig{};
    }

    throw std::invalid_argument("unknown scheduler config: " + name);
}

