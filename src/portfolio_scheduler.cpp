#include "portfolio_scheduler.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>

#include "metrics.h"
#include "scheduler.h"
#include "scheduler_config.h"
#include "validator.h"

namespace {

constexpr std::array<const char*, 8> kPortfolioConfigs = {
    "v1b",
    "v1c",
    "v1d_light",
    "v1d_mid",
    "v1d_strong",
    "wait_first",
    "memory_first",
    "finish_balanced",
};

double normalize(double value, double minimum, double maximum) {
    const double range = maximum - minimum;
    if (range <= 0.0) {
        return 0.0;
    }
    return (value - minimum) / range;
}

}  // namespace

PortfolioScheduler::PortfolioScheduler(const Instance& instance)
    : instance_(instance) {}

PortfolioScheduler::Candidate PortfolioScheduler::run_candidate(
    const std::string& config_name
) const {
    GreedyScheduler scheduler(
        instance_,
        scheduler_config_from_name(config_name)
    );
    std::vector<Assignment> schedule = scheduler.solve();

    Validator validator(instance_.servers, instance_.tasks);
    const ValidationResult validation = validator.validate(schedule);
    if (!validation.is_valid) {
        throw std::runtime_error(
            "portfolio candidate is invalid: " + config_name
        );
    }

    MetricsCalculator metrics(instance_.servers, instance_.tasks);
    Candidate candidate;
    candidate.config_name = config_name;
    candidate.e_wait = metrics.calcWaitMetric(schedule);
    candidate.e_memory_new = metrics.calcMemoryMetricNew(schedule);
    candidate.e_finish = metrics.calcFinishMetric(schedule);
    candidate.schedule = std::move(schedule);
    return candidate;
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
            candidate.normalized_score =
                normalize(candidate.e_wait, min_wait, max_wait) +
                normalize(
                    candidate.e_memory_new,
                    min_memory,
                    max_memory
                ) +
                normalize(
                    static_cast<double>(candidate.e_finish),
                    min_finish,
                    max_finish
                );
        }

        const auto best = std::min_element(
            candidates.begin(),
            candidates.end(),
            [](const Candidate& left, const Candidate& right) {
                if (left.normalized_score != right.normalized_score) {
                    return left.normalized_score < right.normalized_score;
                }
                return left.config_name < right.config_name;
            }
        );
        selected_config_ = best->config_name;
        return best->schedule;
    } catch (const std::exception&) {
        return fallback_to_v1c();
    }
}

const std::string& PortfolioScheduler::selected_config() const {
    return selected_config_;
}
