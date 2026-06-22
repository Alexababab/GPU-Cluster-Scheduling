#include "scheduler.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

GreedyScheduler::GreedyScheduler(const Instance& instance)
    : tasks_(instance.tasks) {
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
            };
            best_gpu_after = gpu_after;
            best_cpu_after = cpu_after;
            best_memory_after = memory_after;
        }
    }

    return best;
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
                choice.gpu_count
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
