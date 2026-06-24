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
        } else {
            throw std::invalid_argument(
                "unknown config key at line " +
                std::to_string(line_number) + ": " + key);
        }
    }

    return config;
}

