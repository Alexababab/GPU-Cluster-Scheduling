#include <exception>
#include <iostream>
#include <sstream>
#include <string>

#include "io.h"
#include "metrics.h"
#include "validator.h"

using namespace std;

int main(int argc, char* argv[]) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    bool quiet = false;
    bool detail = false;
    for (int i = 1; i < argc; ++i) {
        string arg = argv[i];
        if (arg == "--help") {
            cerr << "Usage: validator [--quiet] [--detail]\n";
            cerr << "  Reads instance data + schedule from stdin\n";
            cerr << "  --quiet: only output JSON to stdout\n";
            cerr << "  --detail: output usage diagnostics to stderr\n";
            return 0;
        } else if (arg == "--quiet") {
            quiet = true;
        } else if (arg == "--detail") {
            detail = true;
        }
    }

    try {
        const Instance instance = read_instance(cin);
        if (!quiet) {
            cerr << "[info] " << instance.servers.size() << " servers, "
                 << instance.tasks.size() << " tasks\n";
        }

        vector<Assignment> schedule;
        int task_id, server_id, gpu_count;
        long long start_time, finish_time;
        while (cin >> task_id >> server_id >> start_time >> gpu_count >> finish_time) {
            schedule.push_back({task_id, server_id, start_time, gpu_count, finish_time});
        }

        if (schedule.empty()) {
            cerr << "error: no schedule data read\n";
            return 1;
        }

        Validator validator(instance.servers, instance.tasks);
        ValidationResult vresult = validator.validate(schedule);

        if (vresult.is_valid) {
            if (!quiet) cerr << "[PASS] schedule is valid!\n";
        } else {
            if (!quiet) {
                cerr << "[FAIL] schedule invalid! " << vresult.errors.size() << " errors:\n";
                for (const auto& err : vresult.errors) {
                    cerr << "  - " << err.message << "\n";
                }
            }
        }

        // JSON output to stdout
        cout << "{\"valid\":" << (vresult.is_valid ? "true" : "false")
             << ",\"errors\":" << vresult.errors.size();

        if (vresult.is_valid) {
            MetricsCalculator calc(instance.servers, instance.tasks);
            ThreeMetrics metrics = calc.calculate(schedule);
            cout << ",\"E_wait\":" << metrics.E_wait
                 << ",\"E_memory\":" << metrics.E_memory
                 << ",\"E_finish\":" << metrics.E_finish;
        }

        cout << "}\n";

        if (!quiet && vresult.is_valid) {
            MetricsCalculator calc(instance.servers, instance.tasks);
            ThreeMetrics metrics = calc.calculate(schedule);
            cerr << "[metrics] E_wait=" << metrics.E_wait
                 << " E_memory=" << metrics.E_memory
                 << " E_finish=" << metrics.E_finish << "\n";
        }

        // Detail diagnostics
        if (detail) {
            cerr << "[diagnostics] total_tasks=" << vresult.total_tasks
                 << " used_servers=" << vresult.used_servers
                 << " makespan=" << vresult.makespan << "\n";
            if (!vresult.server_usages.empty()) {
                cerr << "[diagnostics] server usage:\n";
                for (const auto& su : vresult.server_usages) {
                    cerr << "  S" << su.server_id
                         << ": peak_GPU=" << su.peak_gpu_used
                         << " peak_CPU=" << su.peak_cpu_used
                         << " peak_mem=" << su.peak_memory_used
                         << " util=" << su.utilization_ratio*100 << "%\n";
                }
            }
            // Error category summary
            if (!vresult.errors.empty()) {
                cerr << "[diagnostics] error summary:\n";
                for (const auto& err : vresult.errors) {
                    cerr << "  T" << err.task_id << ": " << err.message << "\n";
                }
            }
        }

        return vresult.is_valid ? 0 : 1;

    } catch (const exception& error) {
        cerr << "error: " << error.what() << "\n";
        return 1;
    }
}
