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
};
