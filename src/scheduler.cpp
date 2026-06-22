#include "scheduler.h"

#include <algorithm>
#include <stdexcept>

namespace {

int ceil_div(int numerator, int denominator) {
    return (numerator + denominator - 1) / denominator;
}

}  // namespace

SequentialBaseline::SequentialBaseline(const Instance& instance)
    : instance_(instance) {}

SequentialBaseline::Placement SequentialBaseline::choose_placement(
    const Task& task
) const {
    Placement best;

    for (const Server& server : instance_.servers) {
        const int gpu_for_memory =
            ceil_div(task.total_gpu_memory, server.gpu_memory);
        const int required_gpu = std::max(task.min_gpu, gpu_for_memory);

        const bool feasible =
            required_gpu <= server.gpu_count &&
            task.cpu_cores <= server.cpu_cores &&
            task.memory <= server.memory;
        if (!feasible) {
            continue;
        }

        if (best.server == nullptr ||
            required_gpu < best.gpu_count ||
            (required_gpu == best.gpu_count && server.id < best.server->id)) {
            best = Placement{&server, required_gpu};
        }
    }

    if (best.server == nullptr) {
        throw std::runtime_error("task has no feasible server");
    }
    return best;
}

std::vector<Assignment> SequentialBaseline::solve() const {
    std::vector<Assignment> schedule;
    schedule.reserve(instance_.tasks.size());

    long long global_available_time = 0;
    for (const Task& task : instance_.tasks) {
        const Placement placement = choose_placement(task);
        const long long start_time =
            std::max(global_available_time, task.release_time);
        const long long finish_time = start_time + task.duration;

        schedule.push_back(Assignment{
            task.id,
            placement.server->id,
            start_time,
            placement.gpu_count,
            finish_time,
        });
        global_available_time = finish_time;
    }

    return schedule;
}

