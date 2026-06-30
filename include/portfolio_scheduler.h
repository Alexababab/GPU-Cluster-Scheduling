#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "model.h"
#include "scheduler_config.h"

class PortfolioScheduler {
public:
    explicit PortfolioScheduler(const Instance& instance);

    std::vector<Assignment> solve();
    std::vector<Assignment> solve_with_repairs();
    const std::string& selected_config() const;
    const std::string& selector_name() const;
    const std::string& valid_candidates() const;

private:
    struct Candidate {
        std::string config_name;
        std::vector<Assignment> schedule;
        double e_wait = 0.0;
        double e_memory_new = 0.0;
        long long e_finish = 0;
        double norm_wait = 0.0;
        double norm_memory = 0.0;
        double norm_finish = 0.0;
        double primary_score = 0.0;
        double secondary_score = 0.0;
    };

    struct RepairBoosts {
        std::unordered_map<int, double> wait_top;
        std::unordered_map<int, double> memory_top;
        std::unordered_map<int, double> finish_tail;
        std::unordered_map<int, double> combo_top;
    };

    Candidate run_candidate(const std::string& config_name) const;
    Candidate run_candidate(
        const std::string& candidate_name,
        SchedulerConfig config,
        std::unordered_map<int, double> task_boosts
    ) const;
    Candidate evaluate_schedule(
        const std::string& candidate_name,
        std::vector<Assignment> schedule
    ) const;
    std::size_t select_best(std::vector<Candidate>& candidates) const;
    RepairBoosts analyze_repairs(
        const std::vector<Assignment>& baseline
    ) const;
    std::vector<Assignment> fallback_to_v1c();

    const Instance& instance_;
    std::string selected_config_ = "v1c";
    std::string selector_name_;
    std::string valid_candidates_;
};
