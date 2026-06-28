#pragma once

#include <queue>
#include <vector>

#include "model.h"
#include "scheduler_config.h"
#include "server_state.h"

class GreedyScheduler {
public:
    explicit GreedyScheduler(
        const Instance& instance,
        SchedulerConfig config = SchedulerConfig{}
    );

    std::vector<Assignment> solve();

private:
    struct FeasiblePlacement {
        int server_index = -1;
        int gpu_count = 0;
    };

    struct TaskFeatures {
        int fit_count = 0;
        int min_required_gpu = 0;
        double scarcity = 0.0;
        double log_area = 0.0;
        double inverse_duration = 0.0;
    };

    struct FinishEvent {
        RunningTask task;

        bool operator>(const FinishEvent& other) const;
    };

    struct StartChoice {
        int server_index = -1;
        int gpu_count = 0;
        double score = 0.0;
    };

    struct ServerScoreBreakdown {
        double gpu_fragment_cost = 0.0;
        double gpu_memory_fragment_cost = 0.0;
        double cpu_fragment_cost = 0.0;
        double memory_fragment_cost = 0.0;
        double residual_imbalance_cost = 0.0;
        double high_capacity_reserve_cost = 0.0;
        double class_mismatch_cost = 0.0;
        double same_class_affinity = 0.0;
        double total = 0.0;
    };

    void build_feasible_placements();
    void build_task_features();
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
    StartChoice choose_start_v0(int task_index) const;
    StartChoice choose_start_scored(int task_index) const;
    double score_pending_task(
        int task_index,
        long long current_time
    ) const;
    bool is_large_task(
        int task_index,
        const FeasiblePlacement& placement
    ) const;
    ServerScoreBreakdown score_server(
        int task_index,
        const FeasiblePlacement& placement
    ) const;
    void order_pending_tasks(
        std::vector<int>& pending_task_indices,
        long long current_time
    ) const;

    SchedulerConfig config_;
    std::vector<Task> tasks_;
    std::vector<ServerState> servers_;
    std::vector<std::vector<FeasiblePlacement>> feasible_placements_;
    std::vector<TaskFeatures> task_features_;
};
