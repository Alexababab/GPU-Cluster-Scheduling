#pragma once

#include <vector>

#include "model.h"

class SequentialBaseline {
public:
    explicit SequentialBaseline(const Instance& instance);

    std::vector<Assignment> solve() const;

private:
    struct Placement {
        const Server* server = nullptr;
        int gpu_count = 0;
    };

    Placement choose_placement(const Task& task) const;

    const Instance& instance_;
};

