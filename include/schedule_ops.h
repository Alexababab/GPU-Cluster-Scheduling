#pragma once

#include <vector>

#include "model.h"
#include "server_state.h"

Assignment remove_task(std::vector<Assignment>& schedule, int task_id);

Assignment try_insert(
    const std::vector<Assignment>& schedule,
    const Task& task,
    const Server& server,
    long long start_time,
    int gpu_count
);

Assignment greedy_insert(
    const std::vector<Assignment>& schedule,
    const Task& task,
    const Server& server,
    int gpu_count,
    long long start_after
);

void rebuild_server_states(
    const std::vector<Assignment>& schedule,
    const std::vector<Server>& servers,
    const std::vector<Task>& tasks,
    long long current_time,
    std::vector<ServerState>& out_states
);