#include "validator.h"

#include <algorithm>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>

using namespace std;

Validator::Validator(const vector<Server>& servers,
                     const vector<Task>& tasks)
    : servers_(servers), tasks_(tasks) {}

ValidationResult Validator::validate(const vector<Assignment>& schedule) const {
    ValidationResult result{true, {}};
    result.total_tasks = static_cast<int>(tasks_.size());
    result.makespan = 0;

    // Run all 8 checks
    checkCompleteness(schedule, result.errors);
    checkReleaseTime(schedule, result.errors);
    checkGpuCount(schedule, result.errors);
    checkGpuMemory(schedule, result.errors);
    checkCpu(schedule, result.errors);
    checkMemory(schedule, result.errors);
    checkFinishTime(schedule, result.errors);
    checkConcurrentResources(schedule, result.errors);

    bool has_fatal = false;
    for (const auto& e : result.errors) {
        // Missing task / wrong count prevents further analysis
        if (e.task_id == 0 && e.message.find("output line count") != string::npos) {
            has_fatal = true;
            break;
        }
    }

    if (!result.errors.empty()) {
        result.is_valid = false;
    }

    // Collect diagnostic statistics even if invalid
    collectDiagnostics(schedule, result);

    return result;
}

void Validator::collectDiagnostics(const vector<Assignment>& schedule,
                                   ValidationResult& result) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    // Makespan
    for (const auto& asgn : schedule) {
        if (asgn.finish_time > result.makespan) {
            result.makespan = asgn.finish_time;
        }
    }

    // Used servers count
    unordered_map<int, int> server_task_count;
    for (const auto& asgn : schedule) {
        if (server_map.count(asgn.server_id)) {
            server_task_count[asgn.server_id]++;
        }
    }
    result.used_servers = static_cast<int>(server_task_count.size());

    // Per-server peak usage
    unordered_map<int, vector<const Assignment*>> by_server;
    for (const auto& asgn : schedule) {
        by_server[asgn.server_id].push_back(&asgn);
    }

    for (const auto& [sid, asgns] : by_server) {
        auto sit = server_map.find(sid);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        // Collect intervals
        struct InternalInterval {
            long long start, end;
            int gpu, cpu, mem;
        };
        vector<InternalInterval> intervals;
        for (const auto* aptr : asgns) {
            auto it = task_map.find(aptr->task_id);
            if (it == task_map.end()) continue;
            intervals.push_back({aptr->start_time, aptr->finish_time,
                                 aptr->gpu_count, it->second.cpu_cores,
                                 it->second.memory});
        }

        // Collect time points
        vector<long long> pts;
        for (const auto& iv : intervals) {
            pts.push_back(iv.start);
            pts.push_back(iv.end);
        }
        sort(pts.begin(), pts.end());
        pts.erase(unique(pts.begin(), pts.end()), pts.end());

        int peak_gpu = 0, peak_cpu = 0, peak_mem = 0;
        double total_gpu_time = 0;
        long long server_total_time = 0;

        for (size_t ti = 0; ti + 1 < pts.size(); ++ti) {
            long long t_start = pts[ti];
            long long t_end = pts[ti + 1];
            if (t_start == t_end) continue;
            long long span = t_end - t_start;

            int sg = 0, sc = 0, sm = 0;
            for (const auto& iv : intervals) {
                if (iv.start < t_end && iv.end > t_start) {
                    sg += iv.gpu;
                    sc += iv.cpu;
                    sm += iv.mem;
                }
            }
            peak_gpu = max(peak_gpu, sg);
            peak_cpu = max(peak_cpu, sc);
            peak_mem = max(peak_mem, sm);

            total_gpu_time += 1.0 * sg * span;
            server_total_time += span;
        }

        double util = 0.0;
        if (server_total_time > 0) {
            util = total_gpu_time / (srv.gpu_count * server_total_time);
        }

        result.server_usages.push_back({sid, peak_gpu, peak_cpu, peak_mem, util});
    }
}

void Validator::checkCompleteness(const vector<Assignment>& schedule,
                                  vector<ValidationError>& errors) const {
    int N = static_cast<int>(tasks_.size());
    int M = static_cast<int>(servers_.size());

    if (static_cast<int>(schedule.size()) != N) {
        ostringstream oss;
        oss << "output line count=" << schedule.size() << ", expected=" << N;
        errors.push_back({oss.str(), 0});
        return;
    }

    set<int> seen;
    for (const auto& asgn : schedule) {
        if (asgn.task_id < 1 || asgn.task_id > N) {
            ostringstream oss;
            oss << "task id " << asgn.task_id << " out of range [1, " << N << "]";
            errors.push_back({oss.str(), asgn.task_id});
        }
        if (seen.count(asgn.task_id)) {
            ostringstream oss;
            oss << "task id " << asgn.task_id << " appears more than once";
            errors.push_back({oss.str(), asgn.task_id});
        }
        seen.insert(asgn.task_id);

        if (asgn.server_id < 1 || asgn.server_id > M) {
            ostringstream oss;
            oss << "server id " << asgn.server_id << " out of range [1, " << M << "]";
            errors.push_back({oss.str(), asgn.task_id});
        }
    }

    for (int tid = 1; tid <= N; ++tid) {
        if (!seen.count(tid)) {
            ostringstream oss;
            oss << "task " << tid << " is missing";
            errors.push_back({oss.str(), tid});
        }
    }
}

void Validator::checkReleaseTime(const vector<Assignment>& schedule,
                                 vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;

    for (const auto& asgn : schedule) {
        auto it = task_map.find(asgn.task_id);
        if (it == task_map.end()) continue;
        if (asgn.start_time < it->second.release_time) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " start=" << asgn.start_time
                << " < release=" << it->second.release_time;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkGpuCount(const vector<Assignment>& schedule,
                              vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    for (const auto& asgn : schedule) {
        auto jit = task_map.find(asgn.task_id);
        if (jit == task_map.end()) continue;
        const Task& task = jit->second;
        auto sit = server_map.find(asgn.server_id);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        if (asgn.gpu_count <= 0) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " gpu_count=" << asgn.gpu_count << " is not positive";
            errors.push_back({oss.str(), asgn.task_id});
        }
        if (asgn.gpu_count < task.min_gpu) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " gpu_count=" << asgn.gpu_count
                << " < min_gpu=" << task.min_gpu;
            errors.push_back({oss.str(), asgn.task_id});
        }
        if (asgn.gpu_count > srv.gpu_count) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " gpu_count=" << asgn.gpu_count
                << " > server " << srv.id << " gpu_count=" << srv.gpu_count;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkGpuMemory(const vector<Assignment>& schedule,
                               vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    for (const auto& asgn : schedule) {
        auto jit = task_map.find(asgn.task_id);
        if (jit == task_map.end()) continue;
        const Task& task = jit->second;
        auto sit = server_map.find(asgn.server_id);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        long long total_gpu_memory = 1LL * asgn.gpu_count * srv.gpu_memory;
        if (task.total_gpu_memory > total_gpu_memory) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " needs " << task.total_gpu_memory
                << " GPU memory, but " << asgn.gpu_count << " GPUs x "
                << srv.gpu_memory << " = " << total_gpu_memory;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkCpu(const vector<Assignment>& schedule,
                         vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    for (const auto& asgn : schedule) {
        auto jit = task_map.find(asgn.task_id);
        if (jit == task_map.end()) continue;
        const Task& task = jit->second;
        auto sit = server_map.find(asgn.server_id);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        if (task.cpu_cores > srv.cpu_cores) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " needs " << task.cpu_cores
                << " CPU > server " << srv.id << " CPU=" << srv.cpu_cores;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkMemory(const vector<Assignment>& schedule,
                            vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    for (const auto& asgn : schedule) {
        auto jit = task_map.find(asgn.task_id);
        if (jit == task_map.end()) continue;
        const Task& task = jit->second;
        auto sit = server_map.find(asgn.server_id);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        if (task.memory > srv.memory) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " needs " << task.memory
                << " memory > server " << srv.id << " memory=" << srv.memory;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkFinishTime(const vector<Assignment>& schedule,
                                vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;

    for (const auto& asgn : schedule) {
        auto jit = task_map.find(asgn.task_id);
        if (jit == task_map.end()) continue;
        const Task& task = jit->second;

        long long expected = asgn.start_time + task.duration;
        if (asgn.finish_time != expected) {
            ostringstream oss;
            oss << "task " << asgn.task_id << " finish=" << asgn.finish_time
                << " != start=" << asgn.start_time << " + duration=" << task.duration
                << " = " << expected;
            errors.push_back({oss.str(), asgn.task_id});
        }
    }
}

void Validator::checkConcurrentResources(const vector<Assignment>& schedule,
                                          vector<ValidationError>& errors) const {
    unordered_map<int, Task> task_map;
    for (const auto& t : tasks_) task_map[t.id] = t;
    unordered_map<int, Server> server_map;
    for (const auto& s : servers_) server_map[s.id] = s;

    unordered_map<int, vector<const Assignment*>> by_server;
    for (const auto& asgn : schedule) {
        by_server[asgn.server_id].push_back(&asgn);
    }

    for (const auto& [sid, asgns] : by_server) {
        auto sit = server_map.find(sid);
        if (sit == server_map.end()) continue;
        const Server& srv = sit->second;

        struct Interval {
            long long start;
            long long end;
            int gpu_count;
            int cpu_cores;
            int memory;
        };
        vector<Interval> intervals;
        for (const auto* asgn_ptr : asgns) {
            auto jit = task_map.find(asgn_ptr->task_id);
            if (jit == task_map.end()) continue;
            const Task& task = jit->second;
            intervals.push_back({
                asgn_ptr->start_time,
                asgn_ptr->finish_time,
                asgn_ptr->gpu_count,
                task.cpu_cores,
                task.memory
            });
        }

        vector<long long> time_points;
        for (const auto& iv : intervals) {
            time_points.push_back(iv.start);
            time_points.push_back(iv.end);
        }
        sort(time_points.begin(), time_points.end());
        time_points.erase(unique(time_points.begin(), time_points.end()),
                          time_points.end());

        for (size_t ti = 0; ti + 1 < time_points.size(); ++ti) {
            long long t_start = time_points[ti];
            long long t_end = time_points[ti + 1];
            if (t_start == t_end) continue;

            int sum_gpu = 0, sum_cpu = 0, sum_memory = 0;
            for (const auto& iv : intervals) {
                if (iv.start < t_end && iv.end > t_start) {
                    sum_gpu += iv.gpu_count;
                    sum_cpu += iv.cpu_cores;
                    sum_memory += iv.memory;
                }
            }

            if (sum_gpu > srv.gpu_count) {
                ostringstream oss;
                oss << "server " << sid << " at [" << t_start << "," << t_end
                    << ") GPU used=" << sum_gpu << " > limit=" << srv.gpu_count;
                errors.push_back({oss.str(), 0});
            }
            if (sum_cpu > srv.cpu_cores) {
                ostringstream oss;
                oss << "server " << sid << " at [" << t_start << "," << t_end
                    << ") CPU used=" << sum_cpu << " > limit=" << srv.cpu_cores;
                errors.push_back({oss.str(), 0});
            }
            if (sum_memory > srv.memory) {
                ostringstream oss;
                oss << "server " << sid << " at [" << t_start << "," << t_end
                    << ") memory used=" << sum_memory << " > limit=" << srv.memory;
                errors.push_back({oss.str(), 0});
            }
        }
    }
}
