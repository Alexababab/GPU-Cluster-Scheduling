#pragma once

#include <queue>
#include <vector>

#include "model.h"
#include "server_state.h"

class GreedyScheduler {
public:
    explicit GreedyScheduler(const Instance& instance);

    std::vector<Assignment> solve();

private:
    struct FeasiblePlacement {
        int server_index = -1;
        int gpu_count = 0;
    };

    struct FinishEvent {
        RunningTask task;

        bool operator>(const FinishEvent& other) const;
    };

    struct StartChoice {
        int server_index = -1;
        int gpu_count = 0;
    };

    void build_feasible_placements();
    void release_finished(
        long long current_time,
        std::priority_queue<
            FinishEvent,
            std::vector<FinishEvent>,
            std::greater<FinishEvent>
        >& finish_events
    );
    bool start_ready_tasks(
        std::vector<int>& pending_task_indices,
        long long current_time,
        std::vector<Assignment>& assignments,
        std::priority_queue<
            FinishEvent,
            std::vector<FinishEvent>,
            std::greater<FinishEvent>
        >& finish_events
    );
    StartChoice choose_start(int task_index) const;

    std::vector<Task> tasks_;
    std::vector<ServerState> servers_;
    std::vector<std::vector<FeasiblePlacement>> feasible_placements_;
};
