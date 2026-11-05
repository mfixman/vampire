#include "Shell/Torok/SearchClock.hpp"
#include <cassert>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <ctime>
#include <thread>

int main(int argc, char**) {
  if (argc > 1) {
    setenv("TOROK_ACTIVE_LRS", "1", 1);
  } else {
    unsetenv("TOROK_ACTIVE_LRS");
  }

  Shell::Torok::startSearchClock();
  assert(Shell::Torok::activeSearchMilliseconds(1000) == 1000);
  std::raise(SIGCONT);

  auto started = std::clock();
  while (std::clock() - started < CLOCKS_PER_SEC / 20) {
  }

  long before = Shell::Torok::activeSearchMilliseconds(1000);
  std::this_thread::sleep_for(std::chrono::milliseconds(150));
  long after = Shell::Torok::activeSearchMilliseconds(2000);
  if (argc > 1) {
    assert(before >= 40 && before < 200);
    assert(after >= before && after < before + 30);
  } else {
    assert(before == 1000 && after == 2000);
  }
}
