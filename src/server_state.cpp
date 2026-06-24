#include "server_state.h"

#include <algorithm>
#include <stdexcept>

namespace {

int ceil_div(int numerator, int denominator) {
    return (numerator + denominator - 1) / denominator;
}

}  // namespace

ServerState::ServerState(Server server)
    : server_(server),
      remaining_gpu_(server.gpu_count),
      remaining_cpu_(server.cpu_cores),
      remaining_memory_(server.memory) {}

int ServerState::required_gpu_count(const Task& task) const {
    const int gpu_for_memory =
        ceil_div(task.total_gpu_memory, server_.gpu_memory);
    return std::max(task.min_gpu, gpu_for_memory);
}

bool ServerState::can_ever_run(const Task& task, int gpu_count) const {
    return gpu_count <= server_.gpu_count &&
           task.cpu_cores <= server_.cpu_cores &&
           task.memory <= server_.memory;
}

bool ServerState::can_start(const Task& task, int gpu_count) const {
    return gpu_count <= remaining_gpu_ &&
           task.cpu_cores <= remaining_cpu_ &&
           task.memory <= remaining_memory_;
}

std::pair<Assignment, RunningTask> ServerState::start(
    const Task& task,
    long long start_time,
    int gpu_count
) {
    if (!can_start(task, gpu_count)) {
        throw std::logic_error("attempted to over-allocate a server");
    }

    remaining_gpu_ -= gpu_count;
    remaining_cpu_ -= task.cpu_cores;
    remaining_memory_ -= task.memory;

    const long long finish_time = start_time + task.duration;
    Assignment assignment{
        task.id,
        server_.id,
        start_time,
        gpu_count,
        finish_time,
    };
    RunningTask running{
        task.id,
        server_.id,
        finish_time,
        gpu_count,
        task.cpu_cores,
        task.memory,
    };
    return {assignment, running};
}

void ServerState::release(const RunningTask& task) {
    if (task.server_id != server_.id) {
        throw std::logic_error("released task on the wrong server");
    }

    remaining_gpu_ += task.gpu_count;
    remaining_cpu_ += task.cpu_cores;
    remaining_memory_ += task.memory;

    if (remaining_gpu_ > server_.gpu_count ||
        remaining_cpu_ > server_.cpu_cores ||
        remaining_memory_ > server_.memory) {
        throw std::logic_error("server resources exceeded capacity on release");
    }
}

const Server& ServerState::server() const {
    return server_;
}

int ServerState::remaining_gpu() const {
    return remaining_gpu_;
}

int ServerState::remaining_cpu() const {
    return remaining_cpu_;
}

int ServerState::remaining_memory() const {
    return remaining_memory_;
}
