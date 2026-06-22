#include <exception>
#include <iostream>

#include "io.h"
#include "scheduler.h"

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    try {
        const Instance instance = read_instance(std::cin);
        const SequentialBaseline scheduler(instance);
        write_schedule(std::cout, scheduler.solve());
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}

