#include "scheduler_config.h"

#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

std::string trim(std::string s) {
    const std::size_t start = s.find_first_not_of(" \t\r");
    if (start == std::string::npos) {
        return "";
    }
    const std::size_t end = s.find_last_not_of(" \t\r");
    return s.substr(start, end - start + 1);
}

double parse_double(const std::string& key, const std::string& value) {
    try {
        return std::stod(value);
    } catch (const std::exception&) {
        throw std::invalid_argument("invalid float value for " + key +
                                    ": " + value);
    }
}

bool parse_bool(const std::string& key, const std::string& value) {
    if (value == "true" || value == "1") {
        return true;
    }
    if (value == "false" || value == "0") {
        return false;
    }
    throw std::invalid_argument("invalid bool value for " + key + ": " +
                                value);
}

ServerSelectionMode parse_server_mode(const std::string& key,
                                      const std::string& value) {
    if (value == "v0" || value == "best_fit" || value == "0") {
        return ServerSelectionMode::V0BestFit;
    }
    if (value == "weighted" || value == "scored" || value == "1") {
        return ServerSelectionMode::WeightedScore;
    }
    throw std::invalid_argument("invalid server mode for " + key + ": " +
                                value);
}

}  // namespace

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

    if (name == "v1c" ||
        name == "v1c_fragmentation_isolation") {
        SchedulerConfig config;
        config.name = "v1c_fragmentation_isolation";
        config.server_score.w_residual_imbalance = 2.0;
        config.isolation_score.enabled = true;
        config.isolation_score.large_task_gpu_threshold = 4;
        config.isolation_score.high_capacity_gpu_threshold = 8;
        config.isolation_score.w_high_capacity_reserve = 5.0;
        config.isolation_score.w_class_mismatch = 3.0;
        config.isolation_score.w_same_class_affinity = 0.75;
        return config;
    }

    if (name == "v1d" || name == "v1d_new_memory_aware_score") {
        SchedulerConfig config =
            scheduler_config_from_name("v1c_fragmentation_isolation");
        config.name = "v1d_new_memory_aware_score";
        config.memory_aware_score.enabled = true;
        config.memory_aware_score.w_duration_memory_waste = 10.0;
        config.memory_aware_score.duration_log_scale = 0.20;
        return config;
    }

    if (name == "v1d_light" || name == "v1d_mid" ||
        name == "v1d_strong") {
        SchedulerConfig config = scheduler_config_from_name("v1d");
        config.name = name;
        if (name == "v1d_light") {
            config.memory_aware_score.w_duration_memory_waste = 4.0;
        } else if (name == "v1d_strong") {
            config.memory_aware_score.w_duration_memory_waste = 15.0;
        }
        return config;
    }

    if (name == "wait_first") {
        SchedulerConfig config = scheduler_config_from_name("v1d_light");
        config.name = name;
        config.task_score.w_priority = 3.0;
        config.task_score.w_wait = 0.035;
        config.task_score.w_scarcity = 50.0;
        config.task_score.w_area = 0.08;
        return config;
    }

    if (name == "memory_first") {
        SchedulerConfig config = scheduler_config_from_name("v1d_strong");
        config.name = name;
        config.server_score.w_gpu_memory_fragment = 4.0;
        config.memory_aware_score.w_duration_memory_waste = 24.0;
        return config;
    }

    if (name == "finish_balanced") {
        SchedulerConfig config = scheduler_config_from_name("v1d_mid");
        config.name = name;
        config.task_score.w_wait = 0.018;
        config.task_score.w_area = 0.85;
        config.task_score.w_short_job = 12.0;
        config.server_score.w_gpu_fragment = 5.0;
        config.server_score.w_residual_imbalance = 1.0;
        return config;
    }

    if (name == "scarcity_first") {
        SchedulerConfig config = scheduler_config_from_name("v1d_light");
        config.name = name;
        config.task_score.w_scarcity = 110.0;
        config.task_score.w_wait = 0.018;
        config.task_score.w_area = 0.12;
        return config;
    }

    if (name == "short_job_first") {
        SchedulerConfig config = scheduler_config_from_name("v1d_light");
        config.name = name;
        config.task_score.w_scarcity = 30.0;
        config.task_score.w_area = 1.15;
        config.task_score.w_short_job = 40.0;
        return config;
    }

    if (name == "heavy_area_first") {
        SchedulerConfig config = scheduler_config_from_name("v1d_mid");
        config.name = name;
        config.task_score.w_wait = 0.022;
        config.task_score.w_area = -0.65;
        config.task_score.w_short_job = 0.0;
        return config;
    }

    if (name == "wait_memory_balance") {
        SchedulerConfig config = scheduler_config_from_name("v1d_mid");
        config.name = name;
        config.task_score.w_wait = 0.028;
        config.memory_aware_score.w_duration_memory_waste = 12.0;
        return config;
    }

    if (name == "finish_aggressive") {
        SchedulerConfig config = scheduler_config_from_name("v1d_light");
        config.name = name;
        config.task_score.w_scarcity = 24.0;
        config.task_score.w_wait = 0.012;
        config.task_score.w_area = 1.55;
        config.task_score.w_short_job = 60.0;
        config.server_score.w_gpu_fragment = 6.0;
        return config;
    }

    if (name == "low_reserve_v1c") {
        SchedulerConfig config = scheduler_config_from_name("v1c");
        config.name = name;
        config.isolation_score.w_high_capacity_reserve = 1.5;
        config.isolation_score.w_class_mismatch = 2.0;
        return config;
    }

    if (name == "high_reserve_v1c") {
        SchedulerConfig config = scheduler_config_from_name("v1c");
        config.name = name;
        config.isolation_score.w_high_capacity_reserve = 9.0;
        config.isolation_score.w_class_mismatch = 4.0;
        config.isolation_score.w_same_class_affinity = 1.0;
        return config;
    }

    if (name == "custom") {
        const char* config_path_env =
            std::getenv("SCHEDULER_CONFIG_FILE");
        const std::string config_path =
            config_path_env == nullptr ? "scheduler_config.txt"
                                       : config_path_env;
        return scheduler_config_from_file(config_path);
    }

    throw std::invalid_argument("unknown scheduler config: " + name);
}

SchedulerConfig scheduler_config_from_file(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::invalid_argument(
            "cannot open scheduler config file: " + path);
    }

    SchedulerConfig config;
    config.name = "custom";

    std::string line;
    int line_number = 0;
    while (std::getline(file, line)) {
        ++line_number;
        const std::string trimmed = trim(line);
        // 跳过空行和注释
        if (trimmed.empty() || trimmed[0] == '#') {
            continue;
        }

        const std::size_t eq = trimmed.find('=');
        if (eq == std::string::npos) {
            throw std::invalid_argument(
                "config line " + std::to_string(line_number) +
                " missing '=': " + trimmed);
        }

        const std::string key = trim(trimmed.substr(0, eq));
        const std::string value = trim(trimmed.substr(eq + 1));

        if (key == "task_scoring_enabled") {
            config.task_score.enabled =
                parse_bool(key, value);
        } else if (key == "w_priority") {
            config.task_score.w_priority =
                parse_double(key, value);
        } else if (key == "w_wait") {
            config.task_score.w_wait = parse_double(key, value);
        } else if (key == "w_scarcity") {
            config.task_score.w_scarcity =
                parse_double(key, value);
        } else if (key == "w_area") {
            config.task_score.w_area = parse_double(key, value);
        } else if (key == "w_short_job") {
            config.task_score.w_short_job =
                parse_double(key, value);
        } else if (key == "server_mode") {
            config.server_score.mode =
                parse_server_mode(key, value);
        } else if (key == "w_gpu_fragment") {
            config.server_score.w_gpu_fragment =
                parse_double(key, value);
        } else if (key == "w_gpu_memory_fragment") {
            config.server_score.w_gpu_memory_fragment =
                parse_double(key, value);
        } else if (key == "w_cpu_fragment") {
            config.server_score.w_cpu_fragment =
                parse_double(key, value);
        } else if (key == "w_memory_fragment") {
            config.server_score.w_memory_fragment =
                parse_double(key, value);
        } else if (key == "w_residual_imbalance") {
            config.server_score.w_residual_imbalance =
                parse_double(key, value);
        } else if (key == "isolation_enabled") {
            config.isolation_score.enabled =
                parse_bool(key, value);
        } else if (key == "large_task_gpu_threshold") {
            config.isolation_score.large_task_gpu_threshold =
                static_cast<int>(parse_double(key, value));
        } else if (key == "high_capacity_gpu_threshold") {
            config.isolation_score.high_capacity_gpu_threshold =
                static_cast<int>(parse_double(key, value));
        } else if (key == "w_high_capacity_reserve") {
            config.isolation_score.w_high_capacity_reserve =
                parse_double(key, value);
        } else if (key == "w_class_mismatch") {
            config.isolation_score.w_class_mismatch =
                parse_double(key, value);
        } else if (key == "w_same_class_affinity") {
            config.isolation_score.w_same_class_affinity =
                parse_double(key, value);
        } else if (key == "memory_aware_enabled") {
            config.memory_aware_score.enabled =
                parse_bool(key, value);
        } else if (key == "w_duration_memory_waste") {
            config.memory_aware_score.w_duration_memory_waste =
                parse_double(key, value);
        } else if (key == "duration_log_scale") {
            config.memory_aware_score.duration_log_scale =
                parse_double(key, value);
        } else {
            throw std::invalid_argument(
                "unknown config key at line " +
                std::to_string(line_number) + ": " + key);
        }
    }

    return config;
}
