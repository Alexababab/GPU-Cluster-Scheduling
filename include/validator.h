#pragma once

#include <string>
#include <vector>

#include "model.h"

struct ValidationError {
    std::string message;
    int task_id; // 0 means global error
};

struct ValidationResult {
    bool is_valid;
    std::vector<ValidationError> errors;
    int total_tasks;
    int used_servers;
    long long makespan;
    // Per-server usage summary: {server_id: gpu_used, cpu_used, memory_used} at peak
    struct ServerUsage {
        int server_id;
        int peak_gpu_used;
        int peak_cpu_used;
        int peak_memory_used;
        double utilization_ratio; // avg GPU used / total GPU over schedule
    };
    std::vector<ServerUsage> server_usages;
};

class Validator {
public:
    Validator(const std::vector<Server>& servers,
              const std::vector<Task>& tasks);

    // Full validation of a schedule
    ValidationResult validate(const std::vector<Assignment>& schedule) const;

private:
    std::vector<Server> servers_;
    std::vector<Task> tasks_;

    // 1. Completeness & uniqueness
    void checkCompleteness(const std::vector<Assignment>& schedule,
                           std::vector<ValidationError>& errors) const;

    // 2. Release time constraint
    void checkReleaseTime(const std::vector<Assignment>& schedule,
                          std::vector<ValidationError>& errors) const;

    // 3. GPU count constraints
    void checkGpuCount(const std::vector<Assignment>& schedule,
                       std::vector<ValidationError>& errors) const;

    // 4. GPU memory constraint
    void checkGpuMemory(const std::vector<Assignment>& schedule,
                        std::vector<ValidationError>& errors) const;

    // 5. CPU constraint
    void checkCpu(const std::vector<Assignment>& schedule,
                  std::vector<ValidationError>& errors) const;

    // 6. Memory constraint
    void checkMemory(const std::vector<Assignment>& schedule,
                     std::vector<ValidationError>& errors) const;

    // 7. Finish time consistency
    void checkFinishTime(const std::vector<Assignment>& schedule,
                         std::vector<ValidationError>& errors) const;

    // 8. Concurrent resource constraint
    void checkConcurrentResources(const std::vector<Assignment>& schedule,
                                  std::vector<ValidationError>& errors) const;

    // Diagnostics: populate result stats even if invalid
    void collectDiagnostics(const std::vector<Assignment>& schedule,
                            ValidationResult& result) const;
};
