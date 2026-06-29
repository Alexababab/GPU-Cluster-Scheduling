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
    for (int i = 1; i < argc; ++i) {
        string arg = argv[i];
        if (arg == "--help") {
            cerr << "Usage: validator [--quiet]\n";
            cerr << "  Reads instance data + schedule from stdin\n";
            cerr << "  --quiet: only output JSON to stdout\n";
            return 0;
        } else if (arg == "--quiet") {
            quiet = true;
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
                 << ",\"E_memory\":" << metrics.E_memory_new
                 << ",\"E_memory_old\":" << metrics.E_memory_old
                 << ",\"E_memory_new\":" << metrics.E_memory_new
                 << ",\"E_finish\":" << metrics.E_finish;
        }

        cout << "}\n";

        if (!quiet && vresult.is_valid) {
            MetricsCalculator calc(instance.servers, instance.tasks);
            ThreeMetrics metrics = calc.calculate(schedule);
            cerr << "[metrics] E_wait=" << metrics.E_wait
                 << " E_memory_old=" << metrics.E_memory_old
                 << " E_memory_new=" << metrics.E_memory_new
                 << " E_finish=" << metrics.E_finish << "\n";
        }

        return vresult.is_valid ? 0 : 1;

    } catch (const exception& error) {
        cerr << "error: " << error.what() << "\n";
        return 1;
    }
}
