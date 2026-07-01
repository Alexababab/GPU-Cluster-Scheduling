#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>

#include "io.h"
#include "portfolio_scheduler.h"
#include "scheduler.h"
#include "scheduler_config.h"

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    try {
        const Instance instance = read_instance(std::cin);
        const char* config_environment = std::getenv("SCHEDULER_CONFIG");
        const std::string config_name =
            config_environment == nullptr ? "v1b" : config_environment;
        if (config_name == "portfolio" ||
            config_name == "portfolio_v2_2" ||
            config_name == "portfolio_v3" ||
            config_name == "portfolio_v3_full" ||
            config_name == "portfolio_v4" ||
            config_name == "portfolio_v5" ||
            config_name == "portfolio_v5_full" ||
            config_name == "portfolio_v6") {
            PortfolioScheduler scheduler(instance);
            std::vector<Assignment> schedule;
            if (config_name == "portfolio_v2_2") {
                schedule = scheduler.solve();
            } else if (config_name == "portfolio_v4") {
                schedule = scheduler.solve_v4();
            } else if (config_name == "portfolio" ||
                       config_name == "portfolio_v6") {
                schedule = scheduler.solve_v6();
            } else if (config_name == "portfolio_v5" ||
                       config_name == "portfolio_v5_full") {
                schedule = scheduler.solve_v5(
                    config_name == "portfolio_v5_full"
                );
            } else {
                schedule = scheduler.solve_with_repairs();
            }
            const char* trace_environment =
                std::getenv("SCHEDULER_TRACE_SELECTION");
            if (trace_environment != nullptr &&
                std::string(trace_environment) == "1") {
                std::cerr << "portfolio_selected="
                          << scheduler.selected_config() << '\n';
                std::cerr << "portfolio_selector="
                          << scheduler.selector_name() << '\n';
                std::cerr << "portfolio_candidates="
                          << scheduler.valid_candidates() << '\n';
                std::cerr << "portfolio_candidate_metrics="
                          << scheduler.candidate_metrics() << '\n';
                std::cerr << "portfolio_profile="
                          << scheduler.case_profile() << '\n';
                std::cerr << "portfolio_cheap_count="
                          << scheduler.cheap_candidate_count() << '\n';
                std::cerr << "portfolio_repair_count="
                          << scheduler.repair_candidate_count() << '\n';
                std::cerr << "portfolio_guard_triggered="
                          << (scheduler.guard_triggered() ? 1 : 0) << '\n';
                std::cerr << "portfolio_aborted_count="
                          << scheduler.aborted_candidate_count() << '\n';
                std::cerr << "portfolio_guard_stage="
                          << scheduler.guard_triggered_stage() << '\n';
            }
            write_schedule(std::cout, schedule);
            return 0;
        }
        GreedyScheduler scheduler(
            instance,
            scheduler_config_from_name(config_name)
        );
        write_schedule(std::cout, scheduler.solve());
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}
