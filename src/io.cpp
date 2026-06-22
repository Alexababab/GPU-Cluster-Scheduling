#include "io.h"

#include <istream>
#include <ostream>
#include <stdexcept>

Instance read_instance(std::istream& input) {
    int server_count = 0;
    int task_count = 0;
    if (!(input >> server_count >> task_count)) {
        throw std::runtime_error("failed to read server/task counts");
    }
    if (server_count <= 0 || task_count < 0) {
        throw std::runtime_error("invalid server/task counts");
    }

    Instance instance;
    instance.servers.reserve(server_count);
    instance.tasks.reserve(task_count);

    for (int index = 0; index < server_count; ++index) {
        Server server;
        server.id = index + 1;
        if (!(input >> server.gpu_count >> server.gpu_memory
                    >> server.cpu_cores >> server.memory)) {
            throw std::runtime_error("failed to read server");
        }
        instance.servers.push_back(server);
    }

    for (int index = 0; index < task_count; ++index) {
        Task task;
        task.id = index + 1;
        if (!(input >> task.release_time >> task.duration >> task.min_gpu
                    >> task.total_gpu_memory >> task.cpu_cores
                    >> task.memory >> task.weight)) {
            throw std::runtime_error("failed to read task");
        }
        instance.tasks.push_back(task);
    }

    return instance;
}

void write_schedule(std::ostream& output, const std::vector<Assignment>& schedule) {
    for (const Assignment& assignment : schedule) {
        output << assignment.task_id << ' '
               << assignment.server_id << ' '
               << assignment.start_time << ' '
               << assignment.gpu_count << ' '
               << assignment.finish_time << '\n';
    }
}

