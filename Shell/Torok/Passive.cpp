#include "Passive.hpp"
#include "Guidance.hpp"
#include "Lib/Random.hpp"

#include <algorithm>
#include <cmath>

Shell::Torok::Passive::~Passive() {
  for (auto& [key, clause] : queue) {
    clause->setStore(Kernel::Clause::NONE);
  }
}

void Shell::Torok::Passive::add(Kernel::Clause* clause) {
  // Exponential clocks implement proportional sampling without rescanning the passive set.
  double uniform = std::max(1e-300, Lib::Random::getDouble(0, 1));
  double arrival = clock - std::log(uniform) / weight(clause);

  auto entry = queue.emplace(std::make_pair(arrival, clause->number()), clause).first;
  positions.emplace(clause, entry);

  addedEvent.fire(clause);
}

void Shell::Torok::Passive::remove(Kernel::Clause* clause) {
  auto found = positions.find(clause);

  if (found == positions.end()) {
    return;
  }

  queue.erase(found->second);
  positions.erase(found);

  removedEvent.fire(clause);
}

Kernel::Clause* Shell::Torok::Passive::popSelected() {
  auto first = queue.begin();
  clock = first->first.first;
  auto clause = first->second;

  positions.erase(clause);
  queue.erase(first);

  selectedEvent.fire(clause);

  return clause;
}
