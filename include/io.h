#pragma once

#include <iosfwd>
#include <vector>

#include "model.h"

Instance read_instance(std::istream& input);
void write_schedule(std::ostream& output, const std::vector<Assignment>& schedule);

