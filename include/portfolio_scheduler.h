#pragma once

#include <cstdint>
#include <chrono>
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
    std::vector<Assignment> solve_v4();
    std::vector<Assignment> solve_v5(bool full_pool = false);
    std::vector<Assignment> solve_v6();
    const std::string& selected_config() const;
    const std::string& selector_name() const;
    const std::string& valid_candidates() const;
    const std::string& candidate_metrics() const;
    const std::string& case_profile() const;
    int cheap_candidate_count() const;
    int repair_candidate_count() const;
    bool guard_triggered() const;
    int aborted_candidate_count() const;
    const std::string& guard_triggered_stage() const;

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

    struct CandidateSpec {
        std::string candidate_name;
        std::string base_config;
        std::string repair_type;
        double bad_task_percent = 5.0;
        double boost_strength = 1.0;
        double memory_weight_scale = 1.0;
        double wait_weight_scale = 1.0;
        double finish_weight_scale = 1.0;
        int round_count = 2;
        bool enabled_by_default = false;
    };

    Candidate run_candidate(const std::string& config_name) const;
    Candidate run_candidate(
        const std::string& candidate_name,
        SchedulerConfig config,
        std::unordered_map<int, double> task_boosts,
        bool reservation_enabled = false
    ) const;
    Candidate run_candidate_until(
        const std::string& candidate_name,
        SchedulerConfig config,
        std::unordered_map<int, double> task_boosts,
        std::chrono::steady_clock::time_point deadline
    ) const;
    Candidate evaluate_schedule(
        const std::string& candidate_name,
        std::vector<Assignment> schedule
    ) const;
    std::size_t select_best(
        std::vector<Candidate>& candidates,
        const Candidate* guarded_baseline = nullptr
    ) const;
    RepairBoosts analyze_repairs(
        const std::vector<Assignment>& baseline,
        double bad_task_percent = 5.0,
        double boost_strength = 1.0
    ) const;
    Candidate run_mined_candidate(
        const CandidateSpec& spec,
        const std::vector<Assignment>& baseline
    ) const;
    std::string classify_case() const;
    SchedulerConfig random_config(
        std::uint64_t& state,
        const std::string& profile,
        int index
    ) const;
    std::vector<Assignment> fallback_to_v1c();

    const Instance& instance_;
    std::string selected_config_ = "v1c";
    std::string selector_name_;
    std::string valid_candidates_;
    std::string candidate_metrics_;
    std::string case_profile_ = "balanced";
    int cheap_candidate_count_ = 0;
    int repair_candidate_count_ = 0;
    bool guard_triggered_ = false;
    int aborted_candidate_count_ = 0;
    std::string guard_triggered_stage_ = "none";
};
