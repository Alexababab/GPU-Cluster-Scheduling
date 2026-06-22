#pragma once

#include <vector>

#include "model.h"

struct ThreeMetrics {
    double E_wait;      // weighted wait time
    double E_memory;    // GPU memory idle
    long long E_finish; // latest finish time
};

class MetricsCalculator {
public:
    MetricsCalculator(const std::vector<Server>& servers,
                      const std::vector<Task>& tasks);

    ThreeMetrics calculate(const std::vector<Assignment>& schedule) const;

private:
    std::vector<Server> servers_;
    std::vector<Task> tasks_;

    double calcWaitMetric(const std::vector<Assignment>& schedule) const;
    double calcMemoryMetric(const std::vector<Assignment>& schedule) const;
    long long calcFinishMetric(const std::vector<Assignment>& schedule) const;
    std::vector<long long> collectTimePoints(const std::vector<Assignment>& schedule) const;
};
