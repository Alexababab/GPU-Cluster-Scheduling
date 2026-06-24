#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "io.h"
#include "metrics.h"
#include "scheduler.h"
#include "validator.h"

namespace fs = std::filesystem;
using namespace std;
using namespace chrono;

struct BenchResult {
    string instance_name;
    bool valid;
    int error_count;
    double E_wait;
    double E_memory;
    long long E_finish;
    double runtime_ms;
};

int main(int argc, char* argv[]) {
    string dataset_dir = "C:/Users/lenovo/Desktop/????????/???";
    string output_csv = "experiments/results/v1_benchmark.csv";
    bool show_progress = true;

    for (int i = 1; i < argc; ++i) {
        string arg = argv[i];
        if (arg == "--dataset" && i+1 < argc) dataset_dir = argv[++i];
        else if (arg == "--output" && i+1 < argc) output_csv = argv[++i];
        else if (arg == "--quiet") show_progress = false;
        else if (arg == "--help") {
            cerr << "Usage: benchmark_runner [--dataset DIR] [--output CSV] [--quiet]\n";
            return 0;
        }
    }

    vector<fs::path> instance_files;
    for (const auto& entry : fs::directory_iterator(dataset_dir)) {
        if (entry.path().extension() == ".in") {
            instance_files.push_back(entry.path());
        }
    }
    sort(instance_files.begin(), instance_files.end());

    if (show_progress) {
        cerr << "[info] Found " << instance_files.size() << " instances in " << dataset_dir << "\n";
        cerr << "[info] Output: " << output_csv << "\n";
    }

    vector<BenchResult> results;
    int valid_count = 0;
    int invalid_count = 0;

    for (const auto& in_path : instance_files) {
        string fname = in_path.filename().string();
        string stem = in_path.stem().string();

        if (show_progress) {
            cerr << "  [" << stem << "] ... " << flush;
        }

        auto start_time = high_resolution_clock::now();

        try {
            ifstream fin(in_path);
            if (!fin) {
                if (show_progress) cerr << "FAIL (cannot open)\n";
                continue;
            }
            Instance instance = read_instance(fin);
            fin.close();

            GreedyScheduler scheduler(instance);
            vector<Assignment> schedule = scheduler.solve();

            Validator validator(instance.servers, instance.tasks);
            ValidationResult vresult = validator.validate(schedule);

            double E_wait = 0, E_memory = 0;
            long long E_finish = 0;
            if (vresult.is_valid) {
                MetricsCalculator calc(instance.servers, instance.tasks);
                ThreeMetrics metrics = calc.calculate(schedule);
                E_wait = metrics.E_wait;
                E_memory = metrics.E_memory;
                E_finish = metrics.E_finish;
            }

            auto elapsed = duration_cast<milliseconds>(
                high_resolution_clock::now() - start_time).count();

            BenchResult br;
            br.instance_name = stem;
            br.valid = vresult.is_valid;
            br.error_count = static_cast<int>(vresult.errors.size());
            br.E_wait = E_wait;
            br.E_memory = E_memory;
            br.E_finish = E_finish;
            br.runtime_ms = static_cast<double>(elapsed);
            results.push_back(br);

            if (vresult.is_valid) {
                valid_count++;
                if (show_progress) {
                    cerr << "OK  E_wait=" << E_wait << " E_memory=" << E_memory
                         << " E_finish=" << E_finish << " (" << elapsed << "ms)\n";
                }
            } else {
                invalid_count++;
                if (show_progress) {
                    cerr << "INVALID errors=" << vresult.errors.size()
                         << " (" << elapsed << "ms)\n";
                }
            }

        } catch (const exception& e) {
            if (show_progress) {
                cerr << "ERROR: " << e.what() << "\n";
            }
            BenchResult br;
            br.instance_name = stem;
            br.valid = false;
            br.error_count = -1;
            br.E_wait = br.E_memory = 0;
            br.E_finish = 0;
            br.runtime_ms = 0;
            results.push_back(br);
        }
    }

    ofstream fout(output_csv);
    fout << "instance,valid,errors,E_wait,E_memory,E_finish,runtime_ms\n";
    for (const auto& r : results) {
        fout << r.instance_name << ","
             << (r.valid ? "true" : "false") << ","
             << r.error_count << ","
             << r.E_wait << ","
             << r.E_memory << ","
             << r.E_finish << ","
             << r.runtime_ms << "\n";
    }
    fout.close();

    if (show_progress) {
        cerr << "\n========================================\n";
        cerr << "Benchmark complete\n";
        cerr << "Total:   " << results.size() << "\n";
        cerr << "Valid:   " << valid_count << "\n";
        cerr << "Invalid: " << invalid_count << "\n";
        cerr << "Output:  " << output_csv << "\n";
        cerr << "========================================\n";
    }

    return invalid_count > 0 ? 1 : 0;
}