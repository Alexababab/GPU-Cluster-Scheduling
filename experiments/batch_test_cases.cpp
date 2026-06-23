// ============================================================
// 批量测试用例运行器
// 遍历 tests/handcrafted/ 下的所有 .in 文件
// 对每个文件：读取实例 + 调度结果，传给验证器检查
// 输出汇总报告
//
// 编译（MSVC）：
//   cl /std:c++17 /EHsc /Iinclude /Fe:build/batch_test_cases.exe
//       experiments/batch_test_cases.cpp src/io.cpp src/validator.cpp src/metrics.cpp
// 用法：
//   build\batch_test_cases.exe
// ============================================================

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "io.h"
#include "metrics.h"
#include "validator.h"

namespace fs = std::filesystem;
using namespace std;
using namespace chrono;

struct TestResult {
    string filename;
    bool expected_valid;  // by naming convention: "tcX_" prefix = invalid expected
    bool is_valid;
    int error_count;
    vector<string> error_messages;
    double run_time_ms;
};

// Parse instance data from a full input string (instance + blank line + schedule)
struct ParsedInput {
    Instance instance;
    vector<Assignment> schedule;
};

ParsedInput parseFullInput(istream& input) {
    // First part: instance data
    Instance instance = read_instance(input);
    
    // Second part: schedule data
    vector<Assignment> schedule;
    int task_id, server_id, gpu_count;
    long long start_time, finish_time;
    while (input >> task_id >> server_id >> start_time >> gpu_count >> finish_time) {
        schedule.push_back({task_id, server_id, start_time, gpu_count, finish_time});
    }
    
    return {instance, schedule};
}

bool hasPrefix(const string& str, const string& prefix) {
    return str.size() >= prefix.size() && str.substr(0, prefix.size()) == prefix;
}

int main(int argc, char* argv[]) {
    string test_dir = "tests/handcrafted";
    if (argc >= 2) {
        test_dir = argv[1];
    }

    // Parse smoke.in to find expected line count
    int expected_schedule_lines = 3; // default for smoke.in

    // Collect all .in files
    vector<fs::path> in_files;
    for (const auto& entry : fs::directory_iterator(test_dir)) {
        if (entry.path().extension() == ".in") {
            in_files.push_back(entry.path());
        }
    }
    sort(in_files.begin(), in_files.end());

    cout << "Found " << in_files.size() << " test files in " << test_dir << "\n\n";

    vector<TestResult> results;

    for (const auto& in_path : in_files) {
        string filename = in_path.filename().string();
        cout << "[" << filename << "] ... " << flush;

        // Read file
        ifstream fin(in_path);
        if (!fin) {
            cout << "FAIL (cannot open)\n";
            continue;
        }

        auto start = high_resolution_clock::now();
        
        try {
            auto [instance, schedule] = parseFullInput(fin);
            fin.close();

            Validator validator(instance.servers, instance.tasks);
            ValidationResult vresult = validator.validate(schedule);

            auto elapsed = duration_cast<microseconds>(
                high_resolution_clock::now() - start).count() / 1000.0;

            // Determine expected valid by filename convention
            // "smoke.in" = expected valid; "tcX_*.in" = expected invalid
            bool expected_valid = (filename == "smoke.in" || 
                                  (!hasPrefix(filename, "tc") && !hasPrefix(filename, "TC")));

            TestResult tr;
            tr.filename = filename;
            tr.expected_valid = expected_valid;
            tr.is_valid = vresult.is_valid;
            tr.error_count = static_cast<int>(vresult.errors.size());
            tr.run_time_ms = elapsed;
            for (const auto& err : vresult.errors) {
                tr.error_messages.push_back(err.message);
            }
            results.push_back(tr);

            if (vresult.is_valid == expected_valid) {
                cout << "PASS";
            } else {
                cout << "FAIL";
            }
            cout << " (expected=" << (expected_valid ? "valid" : "invalid")
                 << ", got=" << (vresult.is_valid ? "valid" : "invalid");
            if (!vresult.is_valid) {
                cout << ", errors=" << vresult.error_count;
            }
            cout << ", " << elapsed << "ms)\n";

            if (vresult.is_valid != expected_valid && !vresult.errors.empty()) {
                for (const auto& err : vresult.errors) {
                    cout << "  - " << err.message << "\n";
                }
            }

        } catch (const exception& e) {
            cout << "ERROR: " << e.what() << "\n";
        }
    }

    // Summary
    cout << "\n========================================\n";
    cout << "          Test Summary\n";
    cout << "========================================\n";
    
    int pass = 0, fail = 0, total = static_cast<int>(results.size());
    for (const auto& r : results) {
        if (r.is_valid == r.expected_valid) pass++;
        else fail++;
    }

    cout << "Total: " << total << "\n";
    cout << "Pass:  " << pass << "\n";
    cout << "Fail:  " << fail << "\n";

    if (fail > 0) {
        cout << "\nFailed tests:\n";
        for (const auto& r : results) {
            if (r.is_valid != r.expected_valid) {
                cout << "  " << r.filename
                     << " (expected=" << (r.expected_valid ? "valid" : "invalid")
                     << ", got=" << (r.is_valid ? "valid" : "invalid") << ")\n";
            }
        }
    }

    cout << "\n";
    return fail > 0 ? 1 : 0;
}
