#include "Soft.hpp"
#include "Guidance.hpp"
#include "Kernel/Clause.hpp"
#include "Lib/Exception.hpp"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <limits>

namespace {
  double strength() {
    static double value = [] {
      const char* setting = std::getenv("TOROK_SOFT");
      if (!setting) {
        return 0.0;
      }

      char* end;
      double result = std::strtod(setting, &end);
      if (*end || !std::isfinite(result) || result < 0) {
        USER_ERROR("TOROK_SOFT must be a nonnegative finite number");
      }

      return result;
    }();
    return value;
  }
}

bool Shell::Torok::softEnabled() {
  return std::getenv("TOROK_SOFT") != nullptr;
}

unsigned Shell::Torok::softWeight(const Kernel::Clause* clause, unsigned original) {
  double multiplier = 1 + strength() * (1 - weight(clause));
  double result = std::ceil(original * multiplier);
  return static_cast<unsigned>(std::min(result, double(std::numeric_limits<unsigned>::max())));
}
