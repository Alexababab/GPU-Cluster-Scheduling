#include "portfolio_scheduler.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <future>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>

#include "metrics.h"
#include "scheduler.h"
#include "scheduler_config.h"
#include "validator.h"

namespace {

constexpr std::array<const char*, 14> kPortfolioConfigs = {
    "v1b",
    "v1c",
    "v1d_light",
    "v1d_strong",
    "wait_first",
    "memory_first",
    "finish_balanced",
    "scarcity_first",
    "short_job_first",
    "heavy_area_first",
    "wait_memory_balance",
    "finish_aggressive",
    "low_reserve_v1c",
    "high_reserve_v1c",
};

constexpr const char* kDefaultSelector = "memory_safe";

constexpr std::array<const char*, 9> kSelectorNames = {
    "equal_sum",
    "rank_sum",
    "wait_safe",
    "memory_safe",
    "finish_safe",
    "no_regret_guard",
    "aggressive_guarded",
    "hard_no_regret",
    "leaderboard_proxy",
};

double normalize(double value, double minimum, double maximum) {
    const double range = maximum - minimum;
    if (range <= 0.0) {
        return 0.0;
    }
    return (value - minimum) / range;
}

std::string resolve_selector() {
    const char* environment =
        std::getenv("SCHEDULER_PORTFOLIO_SELECTOR");
    const std::string requested =
        environment == nullptr ? "" : environment;
    for (const char* selector : kSelectorNames) {
        if (requested == selector) {
            return requested;
        }
    }
    return kDefaultSelector;
}

}  // namespace

PortfolioScheduler::PortfolioScheduler(const Instance& instance)
    : instance_(instance),
      selector_name_(resolve_selector()) {}

PortfolioScheduler::Candidate PortfolioScheduler::run_candidate(
    const std::string& config_name
) const {
    return run_candidate(
        config_name,
        scheduler_config_from_name(config_name),
        {}
    );
}

PortfolioScheduler::Candidate PortfolioScheduler::run_candidate(
    const std::string& candidate_name,
    SchedulerConfig config,
    std::unordered_map<int, double> task_boosts,
    bool reservation_enabled
) const {
    GreedyScheduler scheduler(
        instance_,
        std::move(config),
        std::move(task_boosts),
        ReservationConfig{reservation_enabled, 3, 2}
    );
    return evaluate_schedule(candidate_name, scheduler.solve());
}

PortfolioScheduler::Candidate PortfolioScheduler::evaluate_schedule(
    const std::string& candidate_name,
    std::vector<Assignment> schedule
) const {
    Validator validator(instance_.servers, instance_.tasks);
    const ValidationResult validation = validator.validate(schedule);
    if (!validation.is_valid) {
        throw std::runtime_error(
            "portfolio candidate is invalid: " + candidate_name
        );
    }

    MetricsCalculator metrics(instance_.servers, instance_.tasks);
    Candidate candidate;
    candidate.config_name = candidate_name;
    candidate.e_wait = metrics.calcWaitMetric(schedule);
    candidate.e_memory_new = metrics.calcMemoryMetricNew(schedule);
    candidate.e_finish = metrics.calcFinishMetric(schedule);
    candidate.schedule = std::move(schedule);
    return candidate;
}

PortfolioScheduler::Candidate PortfolioScheduler::run_candidate_until(
    const std::string& candidate_name,
    SchedulerConfig config,
    std::unordered_map<int, double> task_boosts,
    std::chrono::steady_clock::time_point deadline
) const {
    GreedyScheduler scheduler(
        instance_,
        std::move(config),
        std::move(task_boosts),
        ReservationConfig{},
        deadline
    );
    return evaluate_schedule(candidate_name, scheduler.solve());
}

PortfolioScheduler::RepairBoosts PortfolioScheduler::analyze_repairs(
    const std::vector<Assignment>& baseline,
    double bad_task_percent,
    double boost_strength
) const {
    struct TaskBadness {
        int task_id = 0;
        double wait = 0.0;
        double memory = 0.0;
        double finish = 0.0;
        double combo = 0.0;
    };

    std::unordered_map<int, const Task*> tasks;
    for (const Task& task : instance_.tasks) {
        tasks[task.id] = &task;
    }
    std::unordered_map<int, const Server*> servers;
    for (const Server& server : instance_.servers) {
        servers[server.id] = &server;
    }

    std::vector<TaskBadness> badness;
    badness.reserve(baseline.size());
    for (const Assignment& assignment : baseline) {
        const auto task_it = tasks.find(assignment.task_id);
        const auto server_it = servers.find(assignment.server_id);
        if (task_it == tasks.end() || server_it == servers.end()) {
            continue;
        }
        const Task& task = *task_it->second;
        const Server& server = *server_it->second;
        const long long wait = std::max(
            0LL,
            assignment.start_time - task.release_time
        );
        const long long allocated_memory =
            1LL * assignment.gpu_count * server.gpu_memory;
        badness.push_back(TaskBadness{
            task.id,
            static_cast<double>(wait) * task.weight,
            static_cast<double>(task.duration) *
                static_cast<double>(
                    allocated_memory - task.total_gpu_memory
                ),
            static_cast<double>(assignment.finish_time),
            0.0,
        });
    }

    RepairBoosts boosts;
    if (badness.empty()) {
        return boosts;
    }

    auto bounds = [&badness](auto accessor) {
        double minimum = std::numeric_limits<double>::infinity();
        double maximum = -std::numeric_limits<double>::infinity();
        for (const TaskBadness& item : badness) {
            minimum = std::min(minimum, accessor(item));
            maximum = std::max(maximum, accessor(item));
        }
        return std::pair<double, double>{minimum, maximum};
    };

    const auto wait_bounds = bounds(
        [](const TaskBadness& item) { return item.wait; }
    );
    const auto memory_bounds = bounds(
        [](const TaskBadness& item) { return item.memory; }
    );
    const auto finish_bounds = bounds(
        [](const TaskBadness& item) { return item.finish; }
    );
    for (TaskBadness& item : badness) {
        item.combo =
            normalize(item.wait, wait_bounds.first, wait_bounds.second) +
            normalize(
                item.memory,
                memory_bounds.first,
                memory_bounds.second
            ) +
            normalize(
                item.finish,
                finish_bounds.first,
                finish_bounds.second
            );
    }

    auto make_boosts = [
        &badness,
        &bounds,
        bad_task_percent,
        boost_strength
    ](
        auto accessor,
        double alpha
    ) {
        std::vector<TaskBadness> ordered = badness;
        std::sort(
            ordered.begin(),
            ordered.end(),
            [accessor](const TaskBadness& left, const TaskBadness& right) {
                const double left_value = accessor(left);
                const double right_value = accessor(right);
                if (left_value != right_value) {
                    return left_value > right_value;
                }
                return left.task_id < right.task_id;
            }
        );
        const auto metric_bounds = bounds(accessor);
        const std::size_t count = std::max<std::size_t>(1, std::min(
            ordered.size(),
            static_cast<std::size_t>(std::ceil(
                ordered.size() * bad_task_percent / 100.0
            ))
        ));
        std::unordered_map<int, double> result;
        for (std::size_t index = 0;
             index < std::min(count, ordered.size());
             ++index) {
            const double severity = normalize(
                accessor(ordered[index]),
                metric_bounds.first,
                metric_bounds.second
            );
            result[ordered[index].task_id] =
                alpha * boost_strength * (0.25 + 0.75 * severity);
        }
        return result;
    };

    boosts.wait_top = make_boosts(
        [](const TaskBadness& item) { return item.wait; },
        450.0
    );
    boosts.memory_top = make_boosts(
        [](const TaskBadness& item) { return item.memory; },
        280.0
    );
    boosts.finish_tail = make_boosts(
        [](const TaskBadness& item) { return item.finish; },
        360.0
    );
    boosts.combo_top = make_boosts(
        [](const TaskBadness& item) { return item.combo; },
        320.0
    );
    return boosts;
}

std::size_t PortfolioScheduler::select_best(
    std::vector<Candidate>& candidates,
    const Candidate* guarded_baseline
) const {
    if (candidates.empty()) {
        throw std::runtime_error("portfolio has no valid candidates");
    }

    double min_wait = std::numeric_limits<double>::infinity();
    double max_wait = -std::numeric_limits<double>::infinity();
    double min_memory = std::numeric_limits<double>::infinity();
    double max_memory = -std::numeric_limits<double>::infinity();
    double min_finish = std::numeric_limits<double>::infinity();
    double max_finish = -std::numeric_limits<double>::infinity();

    for (const Candidate& candidate : candidates) {
        min_wait = std::min(min_wait, candidate.e_wait);
        max_wait = std::max(max_wait, candidate.e_wait);
        min_memory = std::min(min_memory, candidate.e_memory_new);
        max_memory = std::max(max_memory, candidate.e_memory_new);
        min_finish = std::min(
            min_finish,
            static_cast<double>(candidate.e_finish)
        );
        max_finish = std::max(
            max_finish,
            static_cast<double>(candidate.e_finish)
        );
    }

    for (Candidate& candidate : candidates) {
        candidate.norm_wait =
            normalize(candidate.e_wait, min_wait, max_wait);
        candidate.norm_memory = normalize(
            candidate.e_memory_new,
            min_memory,
            max_memory
        );
        candidate.norm_finish = normalize(
            static_cast<double>(candidate.e_finish),
            min_finish,
            max_finish
        );

        const double equal_sum =
            candidate.norm_wait +
            candidate.norm_memory +
            candidate.norm_finish;
        candidate.secondary_score = equal_sum;

        if (selector_name_ == "hard_no_regret") {
            const bool regresses = guarded_baseline != nullptr && (
                candidate.e_wait > guarded_baseline->e_wait ||
                candidate.e_memory_new > guarded_baseline->e_memory_new ||
                candidate.e_finish > guarded_baseline->e_finish
            );
            candidate.primary_score = regresses
                ? std::numeric_limits<double>::infinity()
                : candidate.norm_wait +
                    1.3 * candidate.norm_memory +
                    candidate.norm_finish;
        } else if (selector_name_ == "leaderboard_proxy") {
            const double denominator = static_cast<double>(
                std::max<std::size_t>(1, candidates.size() - 1)
            );
            double rank_score = 0.0;
            for (const Candidate& other : candidates) {
                rank_score += other.e_wait < candidate.e_wait ? 1.0 : 0.0;
                rank_score += other.e_memory_new < candidate.e_memory_new
                    ? 1.0 : 0.0;
                rank_score += other.e_finish < candidate.e_finish ? 1.0 : 0.0;
            }
            rank_score /= denominator;
            double penalty = 0.0;
            if (guarded_baseline != nullptr) {
                penalty += candidate.e_wait > guarded_baseline->e_wait * 1.010
                    ? 0.35 : 0.0;
                penalty += candidate.e_finish > guarded_baseline->e_finish * 1.006
                    ? 0.25 : 0.0;
                penalty += candidate.e_memory_new >
                    guarded_baseline->e_memory_new * 1.003 ? 0.20 : 0.0;
            }
            candidate.primary_score =
                0.45 * (candidate.norm_wait +
                        1.25 * candidate.norm_memory +
                        candidate.norm_finish) +
                0.55 * rank_score + penalty;
        } else if (selector_name_ == "aggressive_guarded") {
            double penalty = 0.0;
            if (guarded_baseline != nullptr) {
                if (candidate.e_wait > guarded_baseline->e_wait * 1.010) {
                    penalty += 0.35;
                }
                if (candidate.e_finish >
                    guarded_baseline->e_finish * 1.005) {
                    penalty += 0.25;
                }
                if (candidate.e_memory_new >
                    guarded_baseline->e_memory_new * 1.003) {
                    penalty += 0.20;
                }
            }
            candidate.primary_score =
                candidate.norm_wait +
                1.25 * candidate.norm_memory +
                candidate.norm_finish + penalty;
        } else if (selector_name_ == "rank_sum") {
            double rank_sum = 0.0;
            for (const Candidate& other : candidates) {
                rank_sum += other.e_wait < candidate.e_wait ? 1.0 : 0.0;
                rank_sum += other.e_memory_new < candidate.e_memory_new
                                ? 1.0
                                : 0.0;
                rank_sum += other.e_finish < candidate.e_finish ? 1.0 : 0.0;
            }
            candidate.primary_score = rank_sum;
        } else if (selector_name_ == "wait_safe") {
            candidate.primary_score =
                1.3 * candidate.norm_wait +
                candidate.norm_memory + candidate.norm_finish;
        } else if (selector_name_ == "memory_safe") {
            candidate.primary_score =
                candidate.norm_wait +
                1.3 * candidate.norm_memory + candidate.norm_finish;
        } else if (selector_name_ == "finish_safe") {
            candidate.primary_score =
                candidate.norm_wait + candidate.norm_memory +
                1.3 * candidate.norm_finish;
        } else if (selector_name_ == "no_regret_guard") {
            candidate.primary_score = std::max(
                candidate.norm_wait,
                std::max(candidate.norm_memory, candidate.norm_finish)
            );
        } else {
            candidate.primary_score = equal_sum;
        }
    }

    const auto best = std::min_element(
        candidates.begin(),
        candidates.end(),
        [](const Candidate& left, const Candidate& right) {
            if (left.primary_score != right.primary_score) {
                return left.primary_score < right.primary_score;
            }
            if (left.secondary_score != right.secondary_score) {
                return left.secondary_score < right.secondary_score;
            }
            return left.config_name < right.config_name;
        }
    );
    return static_cast<std::size_t>(best - candidates.begin());
}

std::vector<Assignment> PortfolioScheduler::fallback_to_v1c() {
    selected_config_ = "v1c";
    GreedyScheduler fallback(
        instance_,
        scheduler_config_from_name("v1c")
    );
    return fallback.solve();
}

std::vector<Assignment> PortfolioScheduler::solve() {
    try {
        std::vector<Candidate> candidates;
        candidates.reserve(kPortfolioConfigs.size());
        for (const char* config_name : kPortfolioConfigs) {
            try {
                candidates.push_back(run_candidate(config_name));
            } catch (const std::exception&) {
                // A failed or invalid candidate is excluded from selection.
            }
        }

        if (candidates.empty()) {
            return fallback_to_v1c();
        }
        valid_candidates_.clear();
        candidate_metrics_.clear();
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
        }
        const std::size_t best = select_best(candidates);
        selected_config_ = candidates[best].config_name;
        return std::move(candidates[best].schedule);
    } catch (const std::exception&) {
        return fallback_to_v1c();
    }
}

std::vector<Assignment> PortfolioScheduler::solve_with_repairs() {
    std::vector<Assignment> baseline = solve();
    try {
        std::vector<Candidate> candidates;
        candidates.reserve(5);
        candidates.push_back(evaluate_schedule(
            "v2.2_baseline",
            baseline
        ));

        RepairBoosts boosts = analyze_repairs(baseline);

        auto add_repair = [&candidates, this](
            const std::string& candidate_name,
            SchedulerConfig config,
            std::unordered_map<int, double> task_boosts
        ) {
            try {
                candidates.push_back(run_candidate(
                    candidate_name,
                    std::move(config),
                    std::move(task_boosts)
                ));
            } catch (const std::exception&) {
                // A failed repair is discarded; the V2.2 baseline remains.
            }
        };

        SchedulerConfig wait_config =
            scheduler_config_from_name("wait_first");
        wait_config.name = "repair_wait_top";
        wait_config.task_score.w_wait = 0.045;
        wait_config.task_score.w_short_job = 0.0;
        add_repair(
            "repair_wait_top",
            std::move(wait_config),
            std::move(boosts.wait_top)
        );

        SchedulerConfig memory_config =
            scheduler_config_from_name("memory_first");
        memory_config.name = "repair_memory_top";
        memory_config.server_score.w_gpu_memory_fragment = 5.0;
        memory_config.memory_aware_score.w_duration_memory_waste = 28.0;
        add_repair(
            "repair_memory_top",
            std::move(memory_config),
            std::move(boosts.memory_top)
        );

        SchedulerConfig finish_config =
            scheduler_config_from_name("finish_aggressive");
        finish_config.name = "repair_finish_tail";
        finish_config.task_score.w_area = 1.75;
        finish_config.task_score.w_short_job = 80.0;
        add_repair(
            "repair_finish_tail",
            std::move(finish_config),
            std::move(boosts.finish_tail)
        );

        SchedulerConfig combo_config =
            scheduler_config_from_name("wait_memory_balance");
        combo_config.name = "repair_combo";
        add_repair(
            "repair_combo",
            std::move(combo_config),
            std::move(boosts.combo_top)
        );

        valid_candidates_.clear();
        candidate_metrics_.clear();
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
        }
        const std::size_t best = select_best(candidates);
        selected_config_ = candidates[best].config_name;
        return std::move(candidates[best].schedule);
    } catch (const std::exception&) {
        selected_config_ = "v2.2_baseline";
        return baseline;
    }
}

std::vector<Assignment> PortfolioScheduler::solve_v4() {
    std::vector<Assignment> baseline = solve_with_repairs();
    try {
        std::vector<Candidate> candidates;
        candidates.reserve(6);
        candidates.push_back(evaluate_schedule("v3_baseline", baseline));
        RepairBoosts boosts = analyze_repairs(baseline);

        std::vector<std::future<Candidate>> pending_candidates;
        pending_candidates.reserve(5);
        auto add_candidate = [&pending_candidates, this](
            const std::string& name,
            SchedulerConfig config,
            std::unordered_map<int, double> task_boosts,
            bool reservation
        ) {
            pending_candidates.push_back(std::async(
                std::launch::async,
                [this,
                 name,
                 config = std::move(config),
                 task_boosts = std::move(task_boosts),
                 reservation]() mutable {
                    return run_candidate(
                        name,
                        std::move(config),
                        std::move(task_boosts),
                        reservation
                    );
                }
            ));
        };

        SchedulerConfig memory = scheduler_config_from_name("memory_first");
        memory.name = "repair_memory_round2";
        memory.server_score.w_gpu_memory_fragment = 5.5;
        memory.memory_aware_score.w_duration_memory_waste = 30.0;
        add_candidate(
            "repair_memory_round2",
            std::move(memory),
            boosts.memory_top,
            false
        );

        SchedulerConfig combo =
            scheduler_config_from_name("wait_memory_balance");
        combo.name = "repair_combo_round2";
        add_candidate(
            "repair_combo_round2",
            combo,
            boosts.combo_top,
            false
        );

        std::unordered_map<int, double> wait_memory = boosts.memory_top;
        for (const auto& [task_id, value] : boosts.wait_top) {
            wait_memory[task_id] += 0.75 * value;
        }
        SchedulerConfig balanced =
            scheduler_config_from_name("wait_memory_balance");
        balanced.name = "repair_wait_memory_round2";
        balanced.task_score.w_wait *= 1.15;
        add_candidate(
            "repair_wait_memory_round2",
            std::move(balanced),
            std::move(wait_memory),
            false
        );

        SchedulerConfig reservation =
            scheduler_config_from_name("high_reserve_v1c");
        reservation.name = "reservation_backfill";
        add_candidate(
            "reservation_backfill",
            reservation,
            {},
            true
        );

        reservation.name = "reservation_repair_combo";
        add_candidate(
            "reservation_repair_combo",
            std::move(reservation),
            std::move(boosts.combo_top),
            true
        );

        for (std::future<Candidate>& pending : pending_candidates) {
            try {
                candidates.push_back(pending.get());
            } catch (const std::exception&) {
                // V3 remains available when a V4 candidate fails validation.
            }
        }

        valid_candidates_.clear();
        candidate_metrics_.clear();
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
        }
        const std::size_t best = select_best(candidates);
        selected_config_ = candidates[best].config_name;
        return std::move(candidates[best].schedule);
    } catch (const std::exception&) {
        selected_config_ = "v3_baseline";
        return baseline;
    }
}

PortfolioScheduler::Candidate PortfolioScheduler::run_mined_candidate(
    const CandidateSpec& spec,
    const std::vector<Assignment>& baseline
) const {
    auto boosts_for = [&spec](RepairBoosts boosts) {
        if (spec.repair_type == "memory") return boosts.memory_top;
        if (spec.repair_type == "combo") return boosts.combo_top;
        if (spec.repair_type == "finish") return boosts.finish_tail;
        std::unordered_map<int, double> combined = boosts.memory_top;
        for (const auto& [task_id, value] : boosts.wait_top) {
            combined[task_id] += value;
        }
        return combined;
    };

    auto make_config = [&spec]() {
        SchedulerConfig config =
            scheduler_config_from_name(spec.base_config);
        config.name = spec.candidate_name;
        config.task_score.w_wait *= spec.wait_weight_scale;
        config.task_score.w_short_job *= spec.finish_weight_scale;
        config.server_score.w_gpu_memory_fragment *=
            spec.memory_weight_scale;
        config.memory_aware_score.w_duration_memory_waste *=
            spec.memory_weight_scale;
        return config;
    };

    RepairBoosts boosts = analyze_repairs(
        baseline,
        spec.bad_task_percent,
        spec.boost_strength
    );
    Candidate candidate = run_candidate(
        spec.candidate_name,
        make_config(),
        boosts_for(std::move(boosts))
    );
    if (spec.round_count >= 3) {
        RepairBoosts round_three = analyze_repairs(
            candidate.schedule,
            spec.bad_task_percent,
            spec.boost_strength
        );
        candidate = run_candidate(
            spec.candidate_name,
            make_config(),
            boosts_for(std::move(round_three))
        );
    }
    if (spec.repair_type == "finish") {
        const Candidate guard = evaluate_schedule("guard", baseline);
        if (candidate.e_wait > guard.e_wait * 1.010) {
            throw std::runtime_error("finish repair exceeded wait guard");
        }
    }
    return candidate;
}

std::vector<Assignment> PortfolioScheduler::solve_v5(bool full_pool) {
    const auto started_at = std::chrono::steady_clock::now();
    std::vector<Assignment> baseline = solve_v4();
    try {
        const char* requested = std::getenv("SCHEDULER_PORTFOLIO_SELECTOR");
        if (requested == nullptr || *requested == '\0') {
            selector_name_ = "hard_no_regret";
        }
        Candidate baseline_candidate = evaluate_schedule(
            "v4_baseline",
            baseline
        );
        std::vector<Candidate> candidates;
        candidates.push_back(baseline_candidate);

        const std::array<CandidateSpec, 12> specs = {{
            {"memory_r2_p3_b12", "memory_first", "memory", 3, 1.2, 1.10, 1, 1, 2, true},
            {"memory_r2_p5_b16", "memory_first", "memory", 5, 1.6, 1.15, 1, 1, 2, false},
            {"memory_r2_p8_b20", "memory_first", "memory", 8, 2.0, 1.20, 1, 1, 2, false},
            {"memory_r3_p5_b14", "memory_first", "memory", 5, 1.4, 1.15, 1, 1, 3, true},
            {"memory_r3_p8_b18", "memory_first", "memory", 8, 1.8, 1.20, 1, 1, 3, true},
            {"combo_r2_p3_b12", "wait_memory_balance", "combo", 3, 1.2, 1.05, 1.05, 1, 2, true},
            {"combo_r2_p5_b16", "wait_memory_balance", "combo", 5, 1.6, 1.10, 1.05, 1, 2, false},
            {"combo_r2_p8_b20", "wait_memory_balance", "combo", 8, 2.0, 1.15, 1.05, 1, 2, true},
            {"combo_r3_p5_b14", "wait_memory_balance", "combo", 5, 1.4, 1.10, 1.05, 1, 3, true},
            {"wait_memory_r2_p5_b16", "wait_memory_balance", "wait_memory", 5, 1.6, 1.10, 1.15, 1, 2, false},
            {"wait_memory_r2_p8_b20", "wait_memory_balance", "wait_memory", 8, 2.0, 1.15, 1.20, 1, 2, true},
            {"finish_tail_guarded", "finish_balanced", "finish", 5, 1.15, 1, 1, 1.10, 2, false},
        }};

        std::vector<std::future<Candidate>> pending;
        for (const CandidateSpec& spec : specs) {
            if (!full_pool && !spec.enabled_by_default) continue;
            const double elapsed = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started_at
            ).count();
            if (elapsed > 52.0) break;
            pending.push_back(std::async(
                std::launch::async,
                [this, spec, &baseline]() {
                    return run_mined_candidate(spec, baseline);
                }
            ));
        }
        for (std::future<Candidate>& future : pending) {
            try {
                candidates.push_back(future.get());
            } catch (const std::exception&) {
                // Invalid and failed mined candidates are excluded.
            }
        }

        valid_candidates_.clear();
        candidate_metrics_.clear();
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
        }
        const std::size_t best = select_best(
            candidates,
            &baseline_candidate
        );
        selected_config_ = candidates[best].config_name;
        return std::move(candidates[best].schedule);
    } catch (const std::exception&) {
        selected_config_ = "v4_baseline";
        return baseline;
    }
}

std::string PortfolioScheduler::classify_case() const {
    if (instance_.tasks.empty() || instance_.servers.empty()) return "balanced";
    const long long density = static_cast<long long>(instance_.servers.size()) *
        static_cast<long long>(instance_.tasks.size());
    if (instance_.tasks.size() >= 4000 || density >= 250000) {
        return "large_dense";
    }
    auto mean_cv = [](const std::vector<double>& values) {
        const double mean = std::accumulate(values.begin(), values.end(), 0.0) /
            static_cast<double>(values.size());
        double variance = 0.0;
        for (double value : values) variance += (value - mean) * (value - mean);
        variance /= static_cast<double>(values.size());
        return std::pair<double, double>{
            mean,
            mean <= 0.0 ? 0.0 : std::sqrt(variance) / mean,
        };
    };
    std::vector<double> gpu_memory, durations, weights, task_memory, releases;
    double feasible_total = 0.0;
    int high_memory = 0;
    int large_gpu = 0;
    for (const Server& server : instance_.servers) gpu_memory.push_back(server.gpu_memory);
    for (const Task& task : instance_.tasks) {
        durations.push_back(static_cast<double>(task.duration));
        weights.push_back(static_cast<double>(task.weight));
        task_memory.push_back(static_cast<double>(task.total_gpu_memory));
        releases.push_back(static_cast<double>(task.release_time));
        large_gpu += task.min_gpu >= 4 ? 1 : 0;
        for (const Server& server : instance_.servers) {
            const int gpu = std::max(
                task.min_gpu,
                (task.total_gpu_memory + server.gpu_memory - 1) /
                    server.gpu_memory
            );
            if (gpu <= server.gpu_count && task.cpu_cores <= server.cpu_cores &&
                task.memory <= server.memory) {
                feasible_total += 1.0;
                if (task.total_gpu_memory >= server.gpu_memory * 2) high_memory++;
            }
        }
    }
    const auto [gpu_memory_mean, gpu_memory_cv] = mean_cv(gpu_memory);
    const auto [duration_mean, duration_cv] = mean_cv(durations);
    const auto [weight_mean, weight_cv] = mean_cv(weights);
    const auto [memory_mean, memory_cv] = mean_cv(task_memory);
    const auto [release_mean, release_cv] = mean_cv(releases);
    (void)gpu_memory_mean; (void)duration_mean; (void)weight_mean;
    (void)memory_mean; (void)release_mean;
    const double average_fit = feasible_total / instance_.tasks.size();
    const double scarcity = average_fit <= 0.0 ? 1.0 : 1.0 / average_fit;
    const double high_memory_ratio = static_cast<double>(high_memory) /
        std::max(1.0, feasible_total);
    const double large_ratio = static_cast<double>(large_gpu) /
        instance_.tasks.size();
    if (gpu_memory_cv > 0.35 && (average_fit < 4.0 || scarcity > 0.25)) {
        return "heterogeneous_tight";
    }
    if (high_memory_ratio > 0.35 || memory_cv > 1.0) return "memory_dominated";
    if (weight_cv > 0.9 && release_cv > 0.8) return "wait_dominated";
    if (duration_cv > 1.0) return "finish_dominated";
    if (large_ratio > 0.30) return "heterogeneous_tight";
    return "balanced";
}

SchedulerConfig PortfolioScheduler::random_config(
    std::uint64_t& state,
    const std::string& profile,
    int index
) const {
    auto next = [&state]() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        return state;
    };
    auto pick = [&next](const auto& values) {
        return values[next() % values.size()];
    };
    static const std::array<double, 5> priority{1, 2, 3, 4, 6};
    static const std::array<double, 7> wait{.005, .01, .018, .025, .035, .05, .08};
    static const std::array<double, 5> scarcity{10, 25, 50, 80, 120};
    static const std::array<double, 7> area{.02, .05, .08, .15, .35, .65, .95};
    static const std::array<double, 6> short_job{0, 2, 6, 10, 16, 24};
    static const std::array<double, 5> gpu_fragment{1, 2, 3, 5, 8};
    static const std::array<double, 5> gpu_memory_fragment{1, 2, 4, 8, 12};
    static const std::array<double, 4> ordinary_fragment{.25, .5, 1, 2};
    static const std::array<double, 5> imbalance{0, .5, 1, 2, 4};
    static const std::array<double, 6> memory_waste{4, 8, 12, 16, 24, 32};
    static const std::array<double, 5> duration_scale{.05, .10, .20, .35, .50};
    static const std::array<int, 4> large_threshold{2, 3, 4, 5};
    static const std::array<int, 3> capacity_threshold{4, 6, 8};
    static const std::array<double, 6> reserve{0, 1, 3, 5, 8, 12};
    static const std::array<double, 5> mismatch{0, 1, 3, 5, 8};
    static const std::array<double, 4> affinity{0, .5, 1, 2};

    SchedulerConfig config = scheduler_config_from_name("v1d_strong");
    config.name = "v6_seed_" + std::to_string(index);
    config.task_score.w_priority = pick(priority);
    config.task_score.w_wait = pick(wait);
    config.task_score.w_scarcity = pick(scarcity);
    config.task_score.w_area = pick(area);
    config.task_score.w_short_job = pick(short_job);
    config.server_score.w_gpu_fragment = pick(gpu_fragment);
    config.server_score.w_gpu_memory_fragment = pick(gpu_memory_fragment);
    config.server_score.w_cpu_fragment = pick(ordinary_fragment);
    config.server_score.w_memory_fragment = pick(ordinary_fragment);
    config.server_score.w_residual_imbalance = pick(imbalance);
    config.memory_aware_score.enabled = true;
    config.memory_aware_score.w_duration_memory_waste = pick(memory_waste);
    config.memory_aware_score.duration_log_scale = pick(duration_scale);
    config.isolation_score.enabled = true;
    config.isolation_score.large_task_gpu_threshold = pick(large_threshold);
    config.isolation_score.high_capacity_gpu_threshold = pick(capacity_threshold);
    config.isolation_score.w_high_capacity_reserve = pick(reserve);
    config.isolation_score.w_class_mismatch = pick(mismatch);
    config.isolation_score.w_same_class_affinity = pick(affinity);
    if (profile == "memory_dominated") {
        config.server_score.w_gpu_memory_fragment = std::max(8.0, config.server_score.w_gpu_memory_fragment);
        config.memory_aware_score.w_duration_memory_waste = std::max(24.0, config.memory_aware_score.w_duration_memory_waste);
    } else if (profile == "wait_dominated") {
        config.task_score.w_wait = std::max(.035, config.task_score.w_wait);
        config.task_score.w_scarcity = std::max(80.0, config.task_score.w_scarcity);
    } else if (profile == "finish_dominated") {
        config.task_score.w_short_job = std::max(16.0, config.task_score.w_short_job);
        config.task_score.w_area = std::min(.15, config.task_score.w_area);
    } else if (profile == "heterogeneous_tight") {
        config.isolation_score.w_high_capacity_reserve = std::max(8.0, config.isolation_score.w_high_capacity_reserve);
        config.isolation_score.w_class_mismatch = std::max(5.0, config.isolation_score.w_class_mismatch);
    }
    return config;
}

std::vector<Assignment> PortfolioScheduler::solve_v6() {
    const auto started = std::chrono::steady_clock::now();
    const auto hard_deadline = started + std::chrono::seconds(54);
    case_profile_ = classify_case();
    cheap_candidate_count_ = 0;
    repair_candidate_count_ = 0;
    guard_triggered_ = false;
    aborted_candidate_count_ = 0;
    guard_triggered_stage_ = "none";

    std::vector<Assignment> incumbent;
    try {
        const char* requested = std::getenv("SCHEDULER_PORTFOLIO_SELECTOR");
        if (requested == nullptr || *requested == '\0') selector_name_ = "leaderboard_proxy";
        Candidate fast_baseline = run_candidate("fast_v1c", scheduler_config_from_name("v1c"), {});
        incumbent = fast_baseline.schedule;
        std::vector<Candidate> candidates{fast_baseline};
        Candidate guard_reference = fast_baseline;

        auto elapsed = [&started]() {
            return std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started
            ).count();
        };
        auto update_incumbent = [&]() {
            const std::size_t best = select_best(candidates, &guard_reference);
            incumbent = candidates[best].schedule;
            selected_config_ = candidates[best].config_name;
        };

        if (elapsed() < 8.0) {
            try {
                candidates.push_back(run_candidate_until(
                    "fast_v1d_light",
                    scheduler_config_from_name("v1d_light"),
                    {},
                    std::min(hard_deadline, started + std::chrono::seconds(8))
                ));
            } catch (const std::exception&) { ++aborted_candidate_count_; }
        }
        if (elapsed() < 8.0) {
            try {
                SchedulerConfig light = scheduler_config_from_name("memory_first");
                light.name = "memory_first_light";
                light.memory_aware_score.w_duration_memory_waste *= 0.6;
                const std::string light_name = light.name;
                candidates.push_back(run_candidate_until(
                    light_name, std::move(light), {},
                    std::min(hard_deadline, started + std::chrono::seconds(8))
                ));
            } catch (const std::exception&) { ++aborted_candidate_count_; }
        }
        update_incumbent();

        const std::array<CandidateSpec, 3> medium_specs = {{
            {"memory_r2_p3_b12", "memory_first", "memory", 3, 1.2, 1.10, 1, 1, 2, true},
            {"combo_r2_p3_b12", "wait_memory_balance", "combo", 3, 1.2, 1.05, 1.05, 1, 2, true},
            {"memory_r3_p5_b14", "memory_first", "memory", 5, 1.4, 1.15, 1, 1, 3, true},
        }};
        for (const CandidateSpec& spec : medium_specs) {
            if (elapsed() >= 25.0) {
                guard_triggered_ = true;
                guard_triggered_stage_ = "medium";
                break;
            }
            try {
                RepairBoosts boosts = analyze_repairs(
                    incumbent, spec.bad_task_percent, spec.boost_strength
                );
                SchedulerConfig config = scheduler_config_from_name(spec.base_config);
                config.name = spec.candidate_name;
                config.server_score.w_gpu_memory_fragment *= spec.memory_weight_scale;
                config.memory_aware_score.w_duration_memory_waste *= spec.memory_weight_scale;
                auto task_boosts = spec.repair_type == "memory"
                    ? boosts.memory_top : boosts.combo_top;
                Candidate candidate = run_candidate_until(
                    spec.candidate_name,
                    config,
                    task_boosts,
                    hard_deadline
                );
                if (spec.round_count == 3 && elapsed() < 25.0) {
                    RepairBoosts next = analyze_repairs(
                        candidate.schedule,
                        spec.bad_task_percent,
                        spec.boost_strength
                    );
                    candidate = run_candidate_until(
                        spec.candidate_name,
                        std::move(config),
                        std::move(next.memory_top),
                        hard_deadline
                    );
                }
                candidates.push_back(std::move(candidate));
                update_incumbent();
            } catch (const std::exception&) { ++aborted_candidate_count_; }
        }

        if (elapsed() < 25.0 &&
            (case_profile_ != "large_dense" || elapsed() < 5.0)) {
            try {
                std::vector<Assignment> v5_schedule = solve_v5(false);
                selector_name_ = "leaderboard_proxy";
                Candidate v5 = evaluate_schedule("v5_heavy", std::move(v5_schedule));
                candidates.push_back(v5);
                guard_reference = v5;
                update_incumbent();
            } catch (const std::exception&) { ++aborted_candidate_count_; }
        }
        if (elapsed() > 45.0) {
            guard_triggered_ = true;
            guard_triggered_stage_ = "heavy";
        } else {
            std::uint64_t state = 1469598103934665603ULL;
            auto hash_value = [&state](std::uint64_t value) {
                state ^= value; state *= 1099511628211ULL;
            };
            for (const Server& server : instance_.servers) {
                hash_value(server.id); hash_value(server.gpu_count);
                hash_value(server.gpu_memory); hash_value(server.memory);
            }
            for (const Task& task : instance_.tasks) {
                hash_value(task.id); hash_value(task.release_time);
                hash_value(task.duration); hash_value(task.total_gpu_memory);
            }
            std::vector<double> probe_times;
            const int profile_limit = case_profile_ == "large_dense" ? 8 :
                (instance_.tasks.size() >= 1500 ? 25 : 50);
            for (int index = 0; index < 3 && elapsed() < 42.0; ++index) {
                const auto probe_started = std::chrono::steady_clock::now();
                try {
                    SchedulerConfig config = random_config(state, case_profile_, index);
                    const std::string config_name = config.name;
                    candidates.push_back(run_candidate_until(
                        config_name, std::move(config), {}, hard_deadline
                    ));
                    ++cheap_candidate_count_;
                    update_incumbent();
                } catch (const std::exception&) { ++aborted_candidate_count_; }
                probe_times.push_back(std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - probe_started
                ).count());
            }
            const double average_probe = probe_times.empty() ? 100.0 :
                std::accumulate(probe_times.begin(), probe_times.end(), 0.0) /
                    probe_times.size();
            int more = 0;
            if (average_probe <= 4.0 && elapsed() < 42.0) {
                more = static_cast<int>((54.0 - elapsed()) /
                    std::max(average_probe, 0.001));
                more = std::min(more, profile_limit - cheap_candidate_count_);
                if (average_probe > 2.0) more = std::min(more, 3);
            }
            for (int offset = 0; offset < more && elapsed() < 42.0; ++offset) {
                try {
                    SchedulerConfig config = random_config(
                        state, case_profile_, cheap_candidate_count_
                    );
                    const std::string config_name = config.name;
                    candidates.push_back(run_candidate_until(
                        config_name, std::move(config), {}, hard_deadline
                    ));
                    ++cheap_candidate_count_;
                    update_incumbent();
                } catch (const std::exception&) { ++aborted_candidate_count_; }
            }
        }

        double remaining = 54.0 - elapsed();
        int repairs_allowed = remaining > 14.0 ? 3 : (remaining > 8.0 ? 1 : 0);
        select_best(candidates, &guard_reference);
        std::vector<std::size_t> order(candidates.size());
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&candidates](std::size_t left, std::size_t right) {
            return candidates[left].primary_score < candidates[right].primary_score;
        });
        for (int rank = 0; rank < repairs_allowed &&
             rank < static_cast<int>(order.size()); ++rank) {
            if (elapsed() >= 54.0) {
                guard_triggered_ = true;
                guard_triggered_stage_ = "repair";
                break;
            }
            try {
                RepairBoosts boosts = analyze_repairs(
                    candidates[order[rank]].schedule, 5.0, 1.4
                );
                const bool memory = rank != 1;
                std::string name = "safe_top" + std::to_string(rank + 1) +
                    (memory ? "_memory" : "_combo");
                SchedulerConfig config = scheduler_config_from_name(
                    memory ? "memory_first" : "wait_memory_balance"
                );
                config.name = name;
                candidates.push_back(run_candidate_until(
                    name,
                    std::move(config),
                    memory ? std::move(boosts.memory_top) :
                             std::move(boosts.combo_top),
                    hard_deadline
                ));
                ++repair_candidate_count_;
                update_incumbent();
            } catch (const std::exception&) { ++aborted_candidate_count_; }
        }

        if (elapsed() >= 54.0) {
            guard_triggered_ = true;
            guard_triggered_stage_ = "hard_stop";
        }
        valid_candidates_.clear();
        candidate_metrics_.clear();
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
        }
        update_incumbent();
        return incumbent;
    } catch (const std::exception&) {
        if (!incumbent.empty()) return incumbent;
        selected_config_ = "v1c";
        GreedyScheduler fallback(instance_, scheduler_config_from_name("v1c"));
        return fallback.solve();
    }
}

std::vector<Assignment> PortfolioScheduler::solve_v9_lite() {
    const auto started = std::chrono::steady_clock::now();
    std::vector<Assignment> baseline = solve_v6();
    Candidate incumbent = evaluate_schedule("v6_safe_baseline", baseline);
    selected_config_ = incumbent.config_name;

    struct Diagnostic {
        const Task* task = nullptr;
        const Server* server = nullptr;
        const Assignment* assignment = nullptr;
        double wait_cost = 0.0;
        double memory_waste = 0.0;
        int feasible_count = 0;
    };
    std::unordered_map<int, const Task*> tasks;
    std::unordered_map<int, const Server*> servers;
    for (const Task& task : instance_.tasks) tasks[task.id] = &task;
    for (const Server& server : instance_.servers) servers[server.id] = &server;

    std::vector<Diagnostic> diagnostics;
    diagnostics.reserve(baseline.size());
    double total_wait = 0.0;
    double total_memory = 0.0;
    long long min_start = std::numeric_limits<long long>::max();
    for (const Assignment& assignment : baseline) {
        const Task& task = *tasks.at(assignment.task_id);
        const Server& server = *servers.at(assignment.server_id);
        int feasible = 0;
        for (const Server& option : instance_.servers) {
            const int gpu_for_memory = static_cast<int>(
                (task.total_gpu_memory + option.gpu_memory - 1LL) /
                option.gpu_memory
            );
            const int needed_gpu = std::max(task.min_gpu, gpu_for_memory);
            feasible += needed_gpu <= option.gpu_count &&
                task.cpu_cores <= option.cpu_cores &&
                task.memory <= option.memory;
        }
        const double wait = static_cast<double>(std::max(
            0LL, assignment.start_time - task.release_time
        )) * task.weight;
        const double waste = static_cast<double>(task.duration) * std::max(
            0LL,
            1LL * assignment.gpu_count * server.gpu_memory -
                task.total_gpu_memory
        );
        diagnostics.push_back({&task, &server, &assignment, wait, waste, feasible});
        total_wait += wait;
        total_memory += waste;
        min_start = std::min(min_start, assignment.start_time);
    }

    auto descending_wait = diagnostics;
    std::sort(descending_wait.begin(), descending_wait.end(),
        [](const Diagnostic& left, const Diagnostic& right) {
            return left.wait_cost > right.wait_cost;
        });
    auto descending_memory = diagnostics;
    std::sort(descending_memory.begin(), descending_memory.end(),
        [](const Diagnostic& left, const Diagnostic& right) {
            return left.memory_waste > right.memory_waste;
        });
    const std::size_t top5_count = std::max<std::size_t>(
        1, (diagnostics.size() + 19) / 20
    );
    const std::size_t memory_hotspot_count = std::max<std::size_t>(
        1, (diagnostics.size() * 3 + 9) / 10
    );
    const double top1_wait_share = total_wait <= 0.0 ? 0.0 :
        descending_wait.front().wait_cost / total_wait;
    double top5_wait = 0.0;
    for (std::size_t i = 0; i < top5_count; ++i) {
        top5_wait += descending_wait[i].wait_cost;
    }
    const double top5_wait_share = total_wait <= 0.0 ? 0.0 :
        top5_wait / total_wait;
    double top_memory = 0.0;
    for (std::size_t i = 0; i < memory_hotspot_count; ++i) {
        top_memory += descending_memory[i].memory_waste;
    }
    const double memory_hotspot = total_memory <= 0.0 ? 0.0 :
        top_memory / total_memory;

    std::vector<int> weights;
    std::vector<int> feasible_counts;
    for (const Diagnostic& item : diagnostics) {
        weights.push_back(item.task->weight);
        feasible_counts.push_back(item.feasible_count);
    }
    std::sort(weights.begin(), weights.end());
    std::sort(feasible_counts.begin(), feasible_counts.end());
    const int weight_p90 = weights[std::min(
        weights.size() - 1, weights.size() * 9 / 10
    )];
    const int feasible_p25 = feasible_counts[std::min(
        feasible_counts.size() - 1, feasible_counts.size() / 4
    )];
    const Diagnostic& dominant = descending_wait.front();

    const long long tail_span = std::max<long long>(
        1, incumbent.e_finish - min_start
    );
    const long long tail_start = incumbent.e_finish -
        std::max<long long>(1, tail_span / 10);
    std::vector<const Diagnostic*> tail_tasks;
    std::unordered_map<int, int> active_tail_servers;
    for (const Diagnostic& item : diagnostics) {
        if (item.assignment->finish_time >= tail_start) {
            tail_tasks.push_back(&item);
            ++active_tail_servers[item.assignment->server_id];
        }
    }
    const int tail_limit = diagnostics.size() < 1000 ? 80 :
        (diagnostics.size() < 3000 ? 50 : 30);
    const double tail_hotspot = diagnostics.empty() ? 0.0 :
        1.0 - std::min(1.0,
            static_cast<double>(tail_tasks.size()) /
            std::max(1.0, diagnostics.size() * 0.25));

    int shape_mismatch_count = 0;
    for (const Diagnostic& item : diagnostics) {
        const int residual_gpu = item.server->gpu_count -
            item.assignment->gpu_count;
        if (residual_gpu > 0 &&
            (item.task->cpu_cores * item.server->gpu_count >
             item.server->cpu_cores * item.assignment->gpu_count ||
             item.task->memory * item.server->gpu_count >
             item.server->memory * item.assignment->gpu_count)) {
            ++shape_mismatch_count;
        }
    }
    const double stranded_score = diagnostics.empty() ? 0.0 :
        static_cast<double>(shape_mismatch_count) / diagnostics.size();

    std::vector<const Diagnostic*> blockers;
    if (total_wait > 0.0) {
        for (const Diagnostic& item : diagnostics) {
            if (item.task->id == dominant.task->id) continue;
            if (item.assignment->start_time < dominant.assignment->start_time &&
                item.assignment->finish_time > dominant.task->release_time) {
                const Server& option = *item.server;
                const int gpu_for_memory = static_cast<int>(
                    (dominant.task->total_gpu_memory + option.gpu_memory - 1LL) /
                    option.gpu_memory
                );
                if (std::max(dominant.task->min_gpu, gpu_for_memory) <=
                    option.gpu_count) {
                    blockers.push_back(&item);
                }
            }
        }
        std::sort(blockers.begin(), blockers.end(),
            [&dominant](const Diagnostic* left, const Diagnostic* right) {
                const long long left_overlap = std::min(
                    left->assignment->finish_time,
                    dominant.assignment->start_time
                ) - std::max(
                    left->assignment->start_time,
                    dominant.task->release_time
                );
                const long long right_overlap = std::min(
                    right->assignment->finish_time,
                    dominant.assignment->start_time
                ) - std::max(
                    right->assignment->start_time,
                    dominant.task->release_time
                );
                return left_overlap > right_overlap;
            });
        if (blockers.size() > 12) blockers.resize(12);
    }

    const bool tail_trigger = tail_hotspot >= 0.60 &&
        !tail_tasks.empty() && static_cast<int>(tail_tasks.size()) <= tail_limit &&
        active_tail_servers.size() > 1;
    const bool memory_trigger = memory_hotspot >= 0.55 &&
        descending_memory.front().memory_waste > 0.0;
    const bool shape_trigger = stranded_score >= 0.30;
    const bool blocker_trigger = total_wait > 0.0 &&
        (top1_wait_share >= 0.70 || top5_wait_share >= 0.90) &&
        dominant.task->weight >= weight_p90 &&
        dominant.feasible_count <= feasible_p25 &&
        !blockers.empty() && blockers.size() <= 12;

    std::array<int, 4> triggered = {{
        tail_trigger, memory_trigger, shape_trigger, blocker_trigger
    }};
    std::array<int, 4> run = {{0, 0, 0, 0}};
    std::array<int, 4> accepted = {{0, 0, 0, 0}};
    std::array<int, 6> rejected = {{0, 0, 0, 0, 0, 0}};
    int skipped_time = 0;
    const auto patch_deadline = std::min(
        started + std::chrono::seconds(55),
        std::chrono::steady_clock::now() + std::chrono::seconds(12)
    );
    auto elapsed = [&]() {
        return std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started
        ).count();
    };
    auto try_patch = [&](int index, const std::string& name,
                         SchedulerConfig config,
                         std::unordered_map<int, double> boosts) {
        if (!triggered[index]) return;
        if (elapsed() > 52.0 || std::chrono::steady_clock::now() >= patch_deadline) {
            ++skipped_time;
            return;
        }
        ++run[index];
        try {
            const auto candidate_deadline = std::min(
                patch_deadline,
                std::chrono::steady_clock::now() + std::chrono::seconds(5)
            );
            Candidate candidate = run_candidate_until(
                name, std::move(config), std::move(boosts), candidate_deadline
            );
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
            if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
            candidate_metrics_ += candidate.config_name + ":" +
                std::to_string(candidate.e_wait) + ":" +
                std::to_string(candidate.e_memory_new) + ":" +
                std::to_string(candidate.e_finish);
            const double wait_limit = index == 0 ? 1.003 :
                (index == 1 || index == 2 ? 1.005 : 0.50);
            const double memory_limit = index == 0 ? 1.003 :
                (index == 1 ? 0.997 : (index == 2 ? 1.0 : 1.02));
            const double finish_limit = index == 0 ? 1.0 :
                (index == 1 || index == 2 || index == 3 ? 1.002 : 1.005);
            const double wait_slack = incumbent.e_wait == 0.0 ? 8.0 : 0.0;
            const bool wait_ok = candidate.e_wait <=
                incumbent.e_wait * wait_limit + wait_slack;
            const bool memory_ok = candidate.e_memory_new <=
                incumbent.e_memory_new * memory_limit;
            const bool finish_ok = candidate.e_finish <=
                incumbent.e_finish * finish_limit;
            const double proxy =
                (candidate.e_wait - incumbent.e_wait) /
                    std::max(1.0, incumbent.e_wait) +
                1.25 * (candidate.e_memory_new - incumbent.e_memory_new) /
                    std::max(1.0, incumbent.e_memory_new) +
                (static_cast<double>(candidate.e_finish) - incumbent.e_finish) /
                    std::max(1.0, static_cast<double>(incumbent.e_finish));
            if (!wait_ok) ++rejected[0];
            if (!memory_ok) ++rejected[1];
            if (!finish_ok) ++rejected[2];
            if (proxy >= 0.0) ++rejected[3];
            if (wait_ok && memory_ok && finish_ok && proxy < 0.0) {
                incumbent = std::move(candidate);
                selected_config_ = incumbent.config_name;
                ++accepted[index];
            }
        } catch (const std::exception&) {
            ++rejected[5];
            ++aborted_candidate_count_;
        }
    };

    RepairBoosts common = analyze_repairs(baseline, 5.0, 1.0);
    SchedulerConfig tail_config = scheduler_config_from_name("finish_aggressive");
    tail_config.memory_aware_score.enabled = true;
    tail_config.memory_aware_score.w_duration_memory_waste = 8.0;
    try_patch(0, "window_tail_repack", std::move(tail_config), common.finish_tail);

    if (memory_trigger) {
        if (elapsed() > 52.0 || std::chrono::steady_clock::now() >= patch_deadline) {
            ++skipped_time;
        } else {
            ++run[1];
            std::vector<Assignment> rematched = baseline;
            double working_memory = incumbent.e_memory_new;
            const std::size_t task_limit = std::min<std::size_t>(
                90, descending_memory.size()
            );
            for (std::size_t rank = 0; rank < task_limit; ++rank) {
                if (std::chrono::steady_clock::now() >= patch_deadline) break;
                const Diagnostic& hotspot = descending_memory[rank];
                if (hotspot.memory_waste <= 0.0) break;
                auto assignment_it = std::find_if(
                    rematched.begin(), rematched.end(),
                    [&hotspot](const Assignment& assignment) {
                        return assignment.task_id == hotspot.task->id;
                    }
                );
                if (assignment_it == rematched.end()) continue;
                Assignment best_assignment = *assignment_it;
                double best_memory = working_memory;
                for (const Server& option : instance_.servers) {
                    const int gpu_for_memory = static_cast<int>(
                        (hotspot.task->total_gpu_memory + option.gpu_memory - 1LL) /
                        option.gpu_memory
                    );
                    const int gpu_count = std::max(
                        hotspot.task->min_gpu, gpu_for_memory
                    );
                    if (gpu_count > option.gpu_count ||
                        hotspot.task->cpu_cores > option.cpu_cores ||
                        hotspot.task->memory > option.memory) continue;
                    const long long new_waste = 1LL * hotspot.task->duration *
                        (1LL * gpu_count * option.gpu_memory -
                         hotspot.task->total_gpu_memory);
                    const long long old_waste = 1LL * hotspot.task->duration *
                        (1LL * best_assignment.gpu_count *
                         servers.at(best_assignment.server_id)->gpu_memory -
                         hotspot.task->total_gpu_memory);
                    if (new_waste >= old_waste) continue;
                    const Assignment original = *assignment_it;
                    assignment_it->server_id = option.id;
                    assignment_it->gpu_count = gpu_count;
                    try {
                        Candidate trial = evaluate_schedule(
                            "memory_window_probe", rematched
                        );
                        if (trial.e_memory_new < best_memory) {
                            best_memory = trial.e_memory_new;
                            best_assignment = *assignment_it;
                        }
                    } catch (const std::exception&) {
                    }
                    *assignment_it = original;
                }
                *assignment_it = best_assignment;
                working_memory = best_memory;
            }
            std::vector<std::size_t> hotspot_indices;
            for (std::size_t rank = 0; rank < task_limit; ++rank) {
                const int task_id = descending_memory[rank].task->id;
                const auto it = std::find_if(
                    rematched.begin(), rematched.end(),
                    [task_id](const Assignment& assignment) {
                        return assignment.task_id == task_id;
                    }
                );
                if (it != rematched.end()) {
                    hotspot_indices.push_back(
                        static_cast<std::size_t>(it - rematched.begin())
                    );
                }
            }
            for (std::size_t left = 0; left < hotspot_indices.size(); ++left) {
                if (std::chrono::steady_clock::now() >= patch_deadline) break;
                const std::size_t window_end = std::min(
                    hotspot_indices.size(), (left / 30 + 1) * 30
                );
                for (std::size_t right = left + 1;
                     right < window_end; ++right) {
                    if (std::chrono::steady_clock::now() >= patch_deadline) break;
                    Assignment& first = rematched[hotspot_indices[left]];
                    Assignment& second = rematched[hotspot_indices[right]];
                    if (first.server_id == second.server_id) continue;
                    const Task& first_task = *tasks.at(first.task_id);
                    const Task& second_task = *tasks.at(second.task_id);
                    const Server& first_target = *servers.at(second.server_id);
                    const Server& second_target = *servers.at(first.server_id);
                    const int first_gpu = std::max(
                        first_task.min_gpu,
                        static_cast<int>((first_task.total_gpu_memory +
                            first_target.gpu_memory - 1LL) /
                            first_target.gpu_memory)
                    );
                    const int second_gpu = std::max(
                        second_task.min_gpu,
                        static_cast<int>((second_task.total_gpu_memory +
                            second_target.gpu_memory - 1LL) /
                            second_target.gpu_memory)
                    );
                    if (first_gpu > first_target.gpu_count ||
                        second_gpu > second_target.gpu_count ||
                        first_task.cpu_cores > first_target.cpu_cores ||
                        second_task.cpu_cores > second_target.cpu_cores ||
                        first_task.memory > first_target.memory ||
                        second_task.memory > second_target.memory) continue;
                    const Assignment first_original = first;
                    const Assignment second_original = second;
                    first.server_id = first_target.id;
                    first.gpu_count = first_gpu;
                    second.server_id = second_target.id;
                    second.gpu_count = second_gpu;
                    try {
                        Candidate trial = evaluate_schedule(
                            "memory_window_swap_probe", rematched
                        );
                        if (trial.e_memory_new < working_memory) {
                            working_memory = trial.e_memory_new;
                            continue;
                        }
                    } catch (const std::exception&) {
                    }
                    first = first_original;
                    second = second_original;
                }
            }
            try {
                Candidate candidate = evaluate_schedule(
                    "memory_window_repack", std::move(rematched)
                );
                if (!valid_candidates_.empty()) valid_candidates_ += ',';
                valid_candidates_ += candidate.config_name;
                if (!candidate_metrics_.empty()) candidate_metrics_ += ';';
                candidate_metrics_ += candidate.config_name + ":" +
                    std::to_string(candidate.e_wait) + ":" +
                    std::to_string(candidate.e_memory_new) + ":" +
                    std::to_string(candidate.e_finish);
                const bool memory_ok = candidate.e_memory_new <=
                    evaluate_schedule("baseline_guard", baseline).e_memory_new * 0.997;
                if (memory_ok) {
                    incumbent = std::move(candidate);
                    selected_config_ = incumbent.config_name;
                    ++accepted[1];
                } else {
                    ++rejected[1];
                }
            } catch (const std::exception&) {
                ++rejected[4];
            }
        }
    }

    SchedulerConfig shape_config = scheduler_config_from_name("v1d_strong");
    shape_config.server_score.w_residual_imbalance = 5.0;
    shape_config.server_score.w_cpu_fragment = 2.5;
    shape_config.server_score.w_memory_fragment = 2.5;
    try_patch(2, "fgd_tetris_rematch", std::move(shape_config), common.combo_top);

    std::unordered_map<int, double> blocker_boosts;
    blocker_boosts[dominant.task->id] = 5000.0;
    double neighbor_boost = 120.0;
    for (const Diagnostic* blocker : blockers) {
        blocker_boosts[blocker->task->id] = neighbor_boost;
        neighbor_boost *= 0.92;
    }
    SchedulerConfig blocker_config = scheduler_config_from_name("v1d_strong");
    blocker_config.task_score.w_wait = 0.025;
    blocker_config.server_score.w_residual_imbalance = 3.0;
    blocker_config.server_score.w_cpu_fragment = 1.5;
    blocker_config.server_score.w_memory_fragment = 1.5;
    blocker_config.memory_aware_score.enabled = true;
    blocker_config.memory_aware_score.w_duration_memory_waste = 24.0;
    blocker_config.isolation_score.enabled = true;
    blocker_config.isolation_score.w_high_capacity_reserve = 2.0;
    blocker_config.isolation_score.w_class_mismatch = 3.0;
    try_patch(3, "blocker_chain_removal", blocker_config, blocker_boosts);
    if (blocker_trigger && accepted[3] == 0) {
        SchedulerConfig memory32 = blocker_config;
        memory32.memory_aware_score.w_duration_memory_waste = 32.0;
        try_patch(3, "blocker_chain_removal_m32", std::move(memory32),
                  blocker_boosts);
    }
    if (blocker_trigger && accepted[3] == 0) {
        SchedulerConfig memory48 = blocker_config;
        memory48.memory_aware_score.w_duration_memory_waste = 48.0;
        try_patch(3, "blocker_chain_removal_m48", std::move(memory48),
                  blocker_boosts);
    }

    std::ostringstream stats;
    stats << "trigger_tail:" << triggered[0]
          << ";trigger_memory:" << triggered[1]
          << ";trigger_shape:" << triggered[2]
          << ";trigger_blocker:" << triggered[3]
          << ";run_tail:" << run[0]
          << ";run_memory:" << run[1]
          << ";run_shape:" << run[2]
          << ";run_blocker:" << run[3]
          << ";accept_tail:" << accepted[0]
          << ";accept_memory:" << accepted[1]
          << ";accept_shape:" << accepted[2]
          << ";accept_blocker:" << accepted[3]
          << ";reject_wait:" << rejected[0]
          << ";reject_memory:" << rejected[1]
          << ";reject_finish:" << rejected[2]
          << ";reject_proxy:" << rejected[3]
          << ";reject_illegal:" << rejected[4]
          << ";reject_timeout:" << rejected[5]
          << ";skipped_time:" << skipped_time;
    pathology_stats_ = stats.str();
    return incumbent.schedule;
}

const std::string& PortfolioScheduler::selected_config() const {
    return selected_config_;
}

const std::string& PortfolioScheduler::selector_name() const {
    return selector_name_;
}

const std::string& PortfolioScheduler::valid_candidates() const {
    return valid_candidates_;
}

const std::string& PortfolioScheduler::candidate_metrics() const {
    return candidate_metrics_;
}

const std::string& PortfolioScheduler::case_profile() const {
    return case_profile_;
}

int PortfolioScheduler::cheap_candidate_count() const {
    return cheap_candidate_count_;
}

int PortfolioScheduler::repair_candidate_count() const {
    return repair_candidate_count_;
}

bool PortfolioScheduler::guard_triggered() const {
    return guard_triggered_;
}

int PortfolioScheduler::aborted_candidate_count() const {
    return aborted_candidate_count_;
}

const std::string& PortfolioScheduler::guard_triggered_stage() const {
    return guard_triggered_stage_;
}

const std::string& PortfolioScheduler::pathology_stats() const {
    return pathology_stats_;
}
