#include "scheduler.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

GreedyScheduler::GreedyScheduler(
    const Instance& instance,
    SchedulerConfig config
)
    : config_(std::move(config)),
      tasks_(instance.tasks) {
    std::sort(
        tasks_.begin(),
        tasks_.end(),
        [](const Task& left, const Task& right) {
            if (left.release_time != right.release_time) {
                return left.release_time < right.release_time;
            }
            return left.id < right.id;
        }
    );

    std::vector<Server> ordered_servers = instance.servers;
    std::sort(
        ordered_servers.begin(),
        ordered_servers.end(),
        [](const Server& left, const Server& right) {
            return left.id < right.id;
        }
    );
    servers_.reserve(ordered_servers.size());
    for (const Server& server : ordered_servers) {
        servers_.emplace_back(server);
    }

    build_feasible_placements();
    build_task_features();
}

bool GreedyScheduler::FinishEvent::operator>(
    const FinishEvent& other
) const {
    if (task.finish_time != other.task.finish_time) {
        return task.finish_time > other.task.finish_time;
    }
    if (task.server_id != other.task.server_id) {
        return task.server_id > other.task.server_id;
    }
    return task.task_id > other.task.task_id;
}

void GreedyScheduler::build_feasible_placements() {
    feasible_placements_.resize(tasks_.size());

    for (std::size_t task_index = 0;
         task_index < tasks_.size();
         ++task_index) {
        const Task& task = tasks_[task_index];
        auto& placements = feasible_placements_[task_index];

        for (std::size_t server_index = 0;
             server_index < servers_.size();
             ++server_index) {
            const int gpu_count =
                servers_[server_index].required_gpu_count(task);
            if (servers_[server_index].can_ever_run(task, gpu_count)) {
                placements.push_back(FeasiblePlacement{
                    static_cast<int>(server_index),
                    gpu_count,
                });
            }
        }

        if (placements.empty()) {
            throw std::runtime_error("task has no feasible server");
        }
    }
}

void GreedyScheduler::build_task_features() {
    task_features_.resize(tasks_.size());

    for (std::size_t task_index = 0;
         task_index < tasks_.size();
         ++task_index) {
        const Task& task = tasks_[task_index];
        const auto& placements = feasible_placements_[task_index];
        int min_required_gpu = std::numeric_limits<int>::max();
        for (const FeasiblePlacement& placement : placements) {
            min_required_gpu =
                std::min(min_required_gpu, placement.gpu_count);
        }

        const double area =
            static_cast<double>(task.duration) *
            static_cast<double>(min_required_gpu);
        task_features_[task_index] = TaskFeatures{
            static_cast<int>(placements.size()),
            min_required_gpu,
            1.0 / static_cast<double>(placements.size()),
            std::log1p(area),
            1.0 / (1.0 + static_cast<double>(task.duration)),
        };
    }
}

void GreedyScheduler::release_finished(
    long long current_time,
    std::priority_queue<
        FinishEvent,
        std::vector<FinishEvent>,
        std::greater<FinishEvent>
    >& finish_events
) {
    while (!finish_events.empty() &&
           finish_events.top().task.finish_time <= current_time) {
        const RunningTask running = finish_events.top().task;
        finish_events.pop();

        const int server_index = running.server_id - 1;
        if (server_index < 0 ||
            server_index >= static_cast<int>(servers_.size()) ||
            servers_[server_index].server().id != running.server_id) {
            throw std::logic_error("invalid server id in finish event");
        }
        servers_[server_index].release(running);
    }
}

GreedyScheduler::StartChoice GreedyScheduler::choose_start(
    int task_index
) const {
    if (config_.server_score.mode == ServerSelectionMode::V0BestFit) {
        return choose_start_v0(task_index);
    }
    return choose_start_scored(task_index);
}

GreedyScheduler::StartChoice GreedyScheduler::choose_start_v0(
    int task_index
) const {
    if (task_index < 0 ||
        task_index >= static_cast<int>(tasks_.size())) {
        throw std::logic_error("invalid task index");
    }
    const Task& task = tasks_[task_index];

    StartChoice best;
    int best_gpu_after = std::numeric_limits<int>::max();
    int best_cpu_after = std::numeric_limits<int>::max();
    int best_memory_after = std::numeric_limits<int>::max();

    for (const FeasiblePlacement& placement :
         feasible_placements_[static_cast<std::size_t>(task_index)]) {
        const ServerState& server = servers_[placement.server_index];
        if (!server.can_start(task, placement.gpu_count)) {
            continue;
        }

        const int gpu_after =
            server.remaining_gpu() - placement.gpu_count;
        const int cpu_after =
            server.remaining_cpu() - task.cpu_cores;
        const int memory_after =
            server.remaining_memory() - task.memory;

        const bool better =
            best.server_index == -1 ||
            gpu_after < best_gpu_after ||
            (gpu_after == best_gpu_after &&
             cpu_after < best_cpu_after) ||
            (gpu_after == best_gpu_after &&
             cpu_after == best_cpu_after &&
             memory_after < best_memory_after) ||
            (gpu_after == best_gpu_after &&
             cpu_after == best_cpu_after &&
             memory_after == best_memory_after &&
             server.server().id <
                 servers_[best.server_index].server().id);

        if (better) {
            best = StartChoice{
                placement.server_index,
                placement.gpu_count,
                0.0,
            };
            best_gpu_after = gpu_after;
            best_cpu_after = cpu_after;
            best_memory_after = memory_after;
        }
    }

    return best;
}

GreedyScheduler::ServerScoreBreakdown GreedyScheduler::score_server(
    int task_index,
    const FeasiblePlacement& placement
) const {
    const Task& task = tasks_[task_index];
    const ServerState& state = servers_[placement.server_index];
    const Server& server = state.server();

    const int gpu_after =
        state.remaining_gpu() - placement.gpu_count;
    const int cpu_after =
        state.remaining_cpu() - task.cpu_cores;
    const int memory_after =
        state.remaining_memory() - task.memory;
    const int allocated_gpu_memory =
        placement.gpu_count * server.gpu_memory;
    const int unused_allocated_gpu_memory =
        allocated_gpu_memory - task.total_gpu_memory;

    ServerScoreBreakdown score;
    score.gpu_fragment_cost =
        static_cast<double>(gpu_after) /
        static_cast<double>(server.gpu_count);
    score.gpu_memory_fragment_cost =
        static_cast<double>(unused_allocated_gpu_memory) /
        static_cast<double>(server.gpu_count * server.gpu_memory);
    score.cpu_fragment_cost =
        static_cast<double>(cpu_after) /
        static_cast<double>(server.cpu_cores);
    score.memory_fragment_cost =
        static_cast<double>(memory_after) /
        static_cast<double>(server.memory);
    const double gpu_after_ratio = score.gpu_fragment_cost;
    const double cpu_after_ratio = score.cpu_fragment_cost;
    const double memory_after_ratio = score.memory_fragment_cost;
    const double max_after_ratio = std::max(
        gpu_after_ratio,
        std::max(cpu_after_ratio, memory_after_ratio)
    );
    const double min_after_ratio = std::min(
        gpu_after_ratio,
        std::min(cpu_after_ratio, memory_after_ratio)
    );
    score.residual_imbalance_cost = max_after_ratio - min_after_ratio;

    if (config_.isolation_score.enabled) {
        const bool large_task = is_large_task(task_index, placement);
        const bool high_capacity_server =
            server.gpu_count >=
            config_.isolation_score.high_capacity_gpu_threshold;
        const bool server_empty =
            state.remaining_gpu() == server.gpu_count &&
            state.remaining_cpu() == server.cpu_cores &&
            state.remaining_memory() == server.memory;
        const double large_gpu_ratio =
            static_cast<double>(state.large_task_gpu_in_use()) /
            static_cast<double>(server.gpu_count);
        const double small_gpu_ratio =
            static_cast<double>(state.small_task_gpu_in_use()) /
            static_cast<double>(server.gpu_count);

        if (!large_task && high_capacity_server) {
            score.high_capacity_reserve_cost = server_empty ? 1.0 : 0.35;
        }
        if (large_task) {
            score.class_mismatch_cost = small_gpu_ratio;
            score.same_class_affinity = large_gpu_ratio;
        } else {
            score.class_mismatch_cost = large_gpu_ratio;
            score.same_class_affinity = small_gpu_ratio;
        }
    }

    score.total =
        config_.server_score.w_gpu_fragment *
            score.gpu_fragment_cost +
        config_.server_score.w_gpu_memory_fragment *
            score.gpu_memory_fragment_cost +
        config_.server_score.w_cpu_fragment *
            score.cpu_fragment_cost +
        config_.server_score.w_memory_fragment *
            score.memory_fragment_cost +
        config_.server_score.w_residual_imbalance *
            score.residual_imbalance_cost +
        config_.isolation_score.w_high_capacity_reserve *
            score.high_capacity_reserve_cost +
        config_.isolation_score.w_class_mismatch *
            score.class_mismatch_cost -
        config_.isolation_score.w_same_class_affinity *
            score.same_class_affinity;
    return score;
}

GreedyScheduler::StartChoice GreedyScheduler::choose_start_scored(
    int task_index
) const {
    if (task_index < 0 ||
        task_index >= static_cast<int>(tasks_.size())) {
        throw std::logic_error("invalid task index");
    }
    const Task& task = tasks_[task_index];

    StartChoice best;
    double best_score = std::numeric_limits<double>::infinity();

    for (const FeasiblePlacement& placement :
         feasible_placements_[static_cast<std::size_t>(task_index)]) {
        const ServerState& server = servers_[placement.server_index];

        // Filter stage: permanent feasibility is precomputed; this checks
        // current GPU, CPU, and memory availability.
        if (!server.can_start(task, placement.gpu_count)) {
            continue;
        }

        const ServerScoreBreakdown breakdown =
            score_server(task_index, placement);
        const bool better =
            best.server_index == -1 ||
            breakdown.total < best_score ||
            (breakdown.total == best_score &&
             server.server().id <
                 servers_[best.server_index].server().id);
        if (better) {
            best = StartChoice{
                placement.server_index,
                placement.gpu_count,
                breakdown.total,
            };
            best_score = breakdown.total;
        }
    }

    return best;
}

double GreedyScheduler::score_pending_task(
    int task_index,
    long long current_time
) const {
    const Task& task = tasks_[task_index];
    const TaskFeatures& features = task_features_[task_index];
    const long long wait_time =
        std::max(0LL, current_time - task.release_time);

    return
        config_.task_score.w_priority *
            static_cast<double>(task.weight) +
        config_.task_score.w_wait *
            static_cast<double>(wait_time) *
            static_cast<double>(task.weight) +
        config_.task_score.w_scarcity *
            features.scarcity -
        config_.task_score.w_area *
            features.log_area +
        config_.task_score.w_short_job *
            features.inverse_duration;
}

bool GreedyScheduler::is_large_task(
    int task_index,
    const FeasiblePlacement& placement
) const {
    const Task& task = tasks_[task_index];
    return placement.gpu_count >=
               config_.isolation_score.large_task_gpu_threshold ||
           task.min_gpu >= config_.isolation_score.large_task_gpu_threshold;
}

void GreedyScheduler::order_pending_tasks(
    std::vector<int>& pending_task_indices,
    long long current_time
) const {
    if (!config_.task_score.enabled) {
        return;
    }

    std::stable_sort(
        pending_task_indices.begin(),
        pending_task_indices.end(),
        [this, current_time](int left_index, int right_index) {
            const double left_score =
                score_pending_task(left_index, current_time);
            const double right_score =
                score_pending_task(right_index, current_time);
            if (left_score != right_score) {
                return left_score > right_score;
            }
            return tasks_[left_index].id < tasks_[right_index].id;
        }
    );
}

bool GreedyScheduler::start_ready_tasks(
    std::vector<int>& pending_task_indices,
    long long current_time,
    std::vector<Assignment>& assignments,
    std::priority_queue<
        FinishEvent,
        std::vector<FinishEvent>,
        std::greater<FinishEvent>
    >& finish_events
) {
    order_pending_tasks(pending_task_indices, current_time);

    bool started_any = false;
    std::vector<int> still_pending;
    still_pending.reserve(pending_task_indices.size());

    for (const int task_index : pending_task_indices) {
        const Task& task = tasks_[task_index];
        const StartChoice choice = choose_start(task_index);
        if (choice.server_index == -1) {
            still_pending.push_back(task_index);
            continue;
        }

        auto [assignment, running] =
            servers_[choice.server_index].start(
                task,
                current_time,
                choice.gpu_count,
                is_large_task(
                    task_index,
                    FeasiblePlacement{
                        choice.server_index,
                        choice.gpu_count,
                    }
                )
            );
        assignments.push_back(assignment);
        finish_events.push(FinishEvent{running});
        started_any = true;
    }

    pending_task_indices.swap(still_pending);
    return started_any;
}

std::vector<Assignment> GreedyScheduler::solve() {
    if (tasks_.empty()) {
        return {};
    }

    using FinishQueue = std::priority_queue<
        FinishEvent,
        std::vector<FinishEvent>,
        std::greater<FinishEvent>
    >;

    FinishQueue finish_events;
    std::vector<int> pending_task_indices;
    std::vector<Assignment> assignments;
    assignments.reserve(tasks_.size());

    std::size_t next_task_index = 0;
    long long current_time = tasks_.front().release_time;

    while (assignments.size() < tasks_.size()) {
        release_finished(current_time, finish_events);

        while (next_task_index < tasks_.size() &&
               tasks_[next_task_index].release_time <= current_time) {
            pending_task_indices.push_back(
                static_cast<int>(next_task_index)
            );
            ++next_task_index;
        }

        start_ready_tasks(
            pending_task_indices,
            current_time,
            assignments,
            finish_events
        );

        if (assignments.size() == tasks_.size()) {
            break;
        }

        long long next_event_time = std::numeric_limits<long long>::max();
        if (next_task_index < tasks_.size()) {
            next_event_time = std::min(
                next_event_time,
                tasks_[next_task_index].release_time
            );
        }
        if (!finish_events.empty()) {
            next_event_time = std::min(
                next_event_time,
                finish_events.top().task.finish_time
            );
        }
        if (next_event_time == std::numeric_limits<long long>::max() ||
            next_event_time <= current_time) {
            throw std::logic_error("scheduler cannot reach a future event");
        }
        current_time = next_event_time;
    }

    std::sort(
        assignments.begin(),
        assignments.end(),
        [](const Assignment& left, const Assignment& right) {
            return left.task_id < right.task_id;
        }
    );
    return assignments;
}
