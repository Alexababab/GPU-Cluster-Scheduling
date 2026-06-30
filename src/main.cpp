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
            config_name == "portfolio_v3") {
            PortfolioScheduler scheduler(instance);
            const std::vector<Assignment> schedule =
                config_name == "portfolio_v2_2"
                    ? scheduler.solve()
                    : scheduler.solve_with_repairs();
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
