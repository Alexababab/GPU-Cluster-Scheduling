#include "schedule_ops.h"

#include <algorithm>
#include <cstdlib>
#include <limits>
#include <unordered_map>

using namespace std;

Assignment remove_task(vector<Assignment>& schedule, int task_id) {
    for (auto it = schedule.begin(); it != schedule.end(); ++it) {
        if (it->task_id == task_id) {
            Assignment removed = *it;
            schedule.erase(it);
            return removed;
        }
    }
    Assignment not_found;
    not_found.task_id = -1;
    return not_found;
}

static bool overlaps(const Assignment& a, long long start, long long end) {
    return a.start_time < end && a.finish_time > start;
}

Assignment try_insert(
    const vector<Assignment>& schedule,
    const Task& task,
    const Server& server,
    long long start_time,
    int gpu_count
) {
    if (gpu_count <= 0 || gpu_count < task.min_gpu || gpu_count > server.gpu_count) {
        Assignment invalid;
        invalid.task_id = -1;
        return invalid;
    }

    long long total_gpu_memory = 1LL * gpu_count * server.gpu_memory;
    if (task.total_gpu_memory > total_gpu_memory) {
        Assignment invalid;
        invalid.task_id = -1;
        return invalid;
    }

    if (task.cpu_cores > server.cpu_cores || task.memory > server.memory) {
        Assignment invalid;
        invalid.task_id = -1;
        return invalid;
    }

    long long finish_time = start_time + task.duration;
    int concurrent_gpu = gpu_count;
    for (const auto& asgn : schedule) {
        if (asgn.server_id == server.id && overlaps(asgn, start_time, finish_time)) {
            concurrent_gpu += asgn.gpu_count;
        }
    }
    if (concurrent_gpu > server.gpu_count) {
        Assignment invalid;
        invalid.task_id = -1;
        return invalid;
    }

    Assignment result;
    result.task_id = task.id;
    result.server_id = server.id;
    result.start_time = start_time;
    result.gpu_count = gpu_count;
    result.finish_time = finish_time;
    return result;
}

Assignment greedy_insert(
    const vector<Assignment>& schedule,
    const Task& task,
    const Server& server,
    int gpu_count,
    long long start_after
) {
    vector<pair<long long, long long>> intervals;
    for (const auto& asgn : schedule) {
        if (asgn.server_id == server.id) {
            intervals.push_back({asgn.start_time, asgn.finish_time});
        }
    }
    sort(intervals.begin(), intervals.end());

    long long cursor = max(start_after, task.release_time);
    long long duration = task.duration;

    for (const auto& iv : intervals) {
        if (cursor + duration <= iv.first) {
            break;
        }
        cursor = max(cursor, iv.second);
    }

    return try_insert(schedule, task, server, cursor, gpu_count);
}

void rebuild_server_states(
    const vector<Assignment>& schedule,
    const vector<Server>& servers,
    const vector<Task>& tasks,
    long long current_time,
    vector<ServerState>& out_states
) {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks) task_map[t.id] = t;

    out_states.clear();
    out_states.reserve(servers.size());
    for (const auto& srv : servers) {
        out_states.emplace_back(srv);
    }

    for (const auto& asgn : schedule) {
        if (asgn.start_time <= current_time && asgn.finish_time > current_time) {
            auto it = task_map.find(asgn.task_id);
            if (it != task_map.end() && asgn.server_id > 0 &&
                asgn.server_id <= static_cast<int>(out_states.size())) {
                int si = asgn.server_id - 1;
                (void)si;
            }
        }
    }
}