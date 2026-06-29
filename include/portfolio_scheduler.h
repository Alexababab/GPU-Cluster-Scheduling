#pragma once

#include <string>
#include <vector>

#include "model.h"

class PortfolioScheduler {
public:
    explicit PortfolioScheduler(const Instance& instance);

    std::vector<Assignment> solve();
    const std::string& selected_config() const;

private:
    struct Candidate {
        std::string config_name;
        std::vector<Assignment> schedule;
        double e_wait = 0.0;
        double e_memory_new = 0.0;
        long long e_finish = 0;
        double normalized_score = 0.0;
    };

    Candidate run_candidate(const std::string& config_name) const;
    std::vector<Assignment> fallback_to_v1c();

    const Instance& instance_;
    std::string selected_config_ = "v1c";
};
