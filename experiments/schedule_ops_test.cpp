#include <iostream>
#include <sstream>
#include <string>

#include "io.h"
#include "schedule_ops.h"
#include "server_state.h"

using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    istringstream input(
        "2 3\n"
        "2 16 8 32\n"
        "4 24 16 64\n"
        "0 5 1 10 2 8 3\n"
        "1 4 2 40 4 16 5\n"
        "3 2 1 24 8 32 1\n"
        "1 1 0 1 5\n"
        "2 2 2 2 6\n"
        "3 2 3 1 5\n"
    );

    try {
        Instance instance = read_instance(input);

        vector<Assignment> schedule;
        int tid, sid, gc;
        long long st, ft;
        while (input >> tid >> sid >> st >> gc >> ft) {
            schedule.push_back({tid, sid, st, static_cast<int>(gc), ft});
        }

        cout << "=== Original schedule (" << schedule.size() << " tasks) ===\n";
        for (const auto& a : schedule) {
            cout << "  T" << a.task_id << ": S" << a.server_id
                 << " [" << a.start_time << "," << a.finish_time << ")"
                 << " GPUs=" << a.gpu_count << "\n";
        }

        cout << "\n=== Test 1: Remove task 2 ===\n";
        Assignment removed = remove_task(schedule, 2);
        cout << "  Removed: T" << removed.task_id << " from S" << removed.server_id << "\n";
        cout << "  Remaining: " << schedule.size() << " tasks\n";
        cout << (removed.task_id == 2 ? "  PASS" : "  FAIL") << "\n";

        cout << "\n=== Test 2: Remove non-existent task 99 ===\n";
        Assignment not_found = remove_task(schedule, 99);
        cout << "  Result task_id: " << not_found.task_id << "\n";
        cout << (not_found.task_id == -1 ? "  PASS" : "  FAIL") << "\n";

        cout << "\n=== Test 3: Try insert task into occupied slot ===\n";
        Task task2; task2.id = 2; task2.min_gpu = 2; task2.duration = 4;
        task2.total_gpu_memory = 40; task2.cpu_cores = 4; task2.memory = 16;
        task2.release_time = 1; task2.weight = 5;
        Server server2; server2.id = 2; server2.gpu_count = 4;
        server2.gpu_memory = 24; server2.cpu_cores = 16; server2.memory = 64;

        Assignment reinserted = try_insert(schedule, task2, server2, 2, 2);
        cout << "  Insert at [2,6): " << (reinserted.task_id != -1 ? "OK" : "FAILED") << "\n";

        cout << "\n=== Test 4: Greedy insert after time=5 ===\n";
        Assignment greedy_test = greedy_insert(schedule, task2, server2, 2, 5);
        if (greedy_test.task_id != -1) {
            cout << "  Found slot: [" << greedy_test.start_time << "," << greedy_test.finish_time << ")\n";
            cout << "  PASS\n";
        } else {
            cout << "  FAILED\n";
        }

        cout << "\n=== Test 5: Greedy insert with no gap ===\n";
        Assignment no_gap = greedy_insert(schedule, task2, server2, 2, 100);
        cout << "  Start at " << no_gap.start_time << "\n";
        cout << (no_gap.task_id != -1 ? "  FOUND" : "  NONE") << "\n";

        cout << "\n=== All tests done ===\n";
        return 0;

    } catch (const exception& ex) {
        cerr << "ERROR: " << ex.what() << "\n";
        return 1;
    }
}