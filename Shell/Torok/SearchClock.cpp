#include "SearchClock.hpp"
#include <algorithm>
#include <atomic>
#include <csignal>
#include <cstdlib>
#include <ctime>

namespace {
  std::clock_t started = 0;
  std::atomic<bool> resumed{false};
  static_assert(std::atomic<bool>::is_always_lock_free);

  void markResumed(int) {
    resumed.store(true, std::memory_order_relaxed);
  }

  bool enabled() {
    static bool value = std::getenv("TOROK_ACTIVE_LRS") != nullptr;
    return value;
  }
}

void Shell::Torok::startSearchClock() {
  if (enabled()) {
    started = std::clock();
#ifdef SIGCONT
    std::signal(SIGCONT, markResumed);
#endif
  }
}

long Shell::Torok::activeSearchMilliseconds(long wallMilliseconds) {
  if (!enabled() || !resumed.load(std::memory_order_relaxed)) {
    return wallMilliseconds;
  }

  auto current = std::clock();
  if (current == std::clock_t(-1) || started == std::clock_t(-1)) {
    return wallMilliseconds;
  }

  return std::max(1L, static_cast<long>((current - started) * 1000.0 / CLOCKS_PER_SEC));
}
