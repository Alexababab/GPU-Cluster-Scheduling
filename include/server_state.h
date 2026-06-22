#pragma once

#include <utility>
#include <vector>

#include "model.h"

class ServerState {
public:
    explicit ServerState(Server server);

    int required_gpu_count(const Task& task) const;
    bool can_ever_run(const Task& task, int gpu_count) const;
    bool can_start(const Task& task, int gpu_count) const;

    std::pair<Assignment, RunningTask> start(
        const Task& task,
        long long start_time,
        int gpu_count
    );
    void release(const RunningTask& task);

    const Server& server() const;
    int remaining_gpu() const;
    int remaining_cpu() const;
    int remaining_memory() const;

private:
    Server server_;
    int remaining_gpu_ = 0;
    int remaining_cpu_ = 0;
    int remaining_memory_ = 0;
};
