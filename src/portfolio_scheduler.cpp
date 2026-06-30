#include "portfolio_scheduler.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <limits>
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

constexpr std::array<const char*, 6> kSelectorNames = {
    "equal_sum",
    "rank_sum",
    "wait_safe",
    "memory_safe",
    "finish_safe",
    "no_regret_guard",
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
    std::unordered_map<int, double> task_boosts
) const {
    GreedyScheduler scheduler(
        instance_,
        std::move(config),
        std::move(task_boosts)
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

PortfolioScheduler::RepairBoosts PortfolioScheduler::analyze_repairs(
    const std::vector<Assignment>& baseline
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

    auto make_boosts = [&badness, &bounds](
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
        const std::size_t count = std::max<std::size_t>(
            1,
            (ordered.size() + 19) / 20
        );
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
                alpha * (0.25 + 0.75 * severity);
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
    std::vector<Candidate>& candidates
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

        if (selector_name_ == "rank_sum") {
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
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
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
        for (const Candidate& candidate : candidates) {
            if (!valid_candidates_.empty()) valid_candidates_ += ',';
            valid_candidates_ += candidate.config_name;
        }
        const std::size_t best = select_best(candidates);
        selected_config_ = candidates[best].config_name;
        return std::move(candidates[best].schedule);
    } catch (const std::exception&) {
        selected_config_ = "v2.2_baseline";
        return baseline;
    }
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
