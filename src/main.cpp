#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>

#include "io.h"
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
