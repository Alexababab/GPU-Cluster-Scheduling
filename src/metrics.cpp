#include "metrics.h"

#include <algorithm>
#include <map>
#include <unordered_map>

using namespace std;

MetricsCalculator::MetricsCalculator(const vector<Server>& servers,
                                     const vector<Task>& tasks)
    : servers_(servers), tasks_(tasks) {}

ThreeMetrics MetricsCalculator::calculate(const vector<Assignment>& schedule) const {
    return {
        calcWaitMetric(schedule),
        calcMemoryMetric(schedule),
        calcFinishMetric(schedule)
    };
}

double MetricsCalculator::calcWaitMetric(const vector<Assignment>& schedule) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;

    double total = 0.0;
    for (const auto& asgn : schedule) {
        auto it = task_map.find(asgn.task_id);
        if (it == task_map.end()) continue;
        const Task& task = it->second;

        long long wait = asgn.start_time - task.release_time;
        if (wait < 0) wait = 0;
        total += 1.0 * wait * task.weight;
    }
    return total;
}

double MetricsCalculator::calcMemoryMetric(const vector<Assignment>& schedule) const {
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;

    vector<long long> time_points = collectTimePoints(schedule);
    if (time_points.size() < 2) return 0.0;

    unordered_map<int, vector<const Assignment*>> by_server;
    for (const auto& asgn : schedule) {
        by_server[asgn.server_id].push_back(&asgn);
    }

    double total_idle = 0.0;
    long long total_span = 0;

    for (size_t ti = 0; ti + 1 < time_points.size(); ++ti) {
        long long t_start = time_points[ti];
        long long t_end = time_points[ti + 1];
        if (t_start == t_end) continue;
        long long interval = t_end - t_start;

        double interval_idle = 0.0;
        for (const Server& srv : servers_) {
            const auto assignments_it = by_server.find(srv.id);

            int used = 0;
            if (assignments_it != by_server.end()) {
                for (const auto* asgn_ptr : assignments_it->second) {
                    if (asgn_ptr->start_time < t_end &&
                        asgn_ptr->finish_time > t_start) {
                        auto jit = task_map.find(asgn_ptr->task_id);
                        if (jit != task_map.end()) {
                            used += jit->second.total_gpu_memory;
                        }
                    }
                }
            }
            int total = srv.gpu_count * srv.gpu_memory;
            int idle = total - used;
            if (idle < 0) idle = 0;
            interval_idle += idle;
        }

        total_idle += interval_idle * interval;
        total_span += interval;
    }

    if (total_span == 0) return 0.0;
    return total_idle / static_cast<double>(total_span);
}

long long MetricsCalculator::calcFinishMetric(const vector<Assignment>& schedule) const {
    long long max_finish = 0;
    for (const auto& asgn : schedule) {
        if (asgn.finish_time > max_finish) max_finish = asgn.finish_time;
    }
    return max_finish;
}

vector<long long> MetricsCalculator::collectTimePoints(const vector<Assignment>& schedule) const {
    vector<long long> points{0};
    for (const auto& asgn : schedule) {
        points.push_back(asgn.start_time);
        points.push_back(asgn.finish_time);
    }
    for (const auto& t : tasks_) {
        points.push_back(t.release_time);
    }
    sort(points.begin(), points.end());
    points.erase(unique(points.begin(), points.end()), points.end());
    return points;
}
