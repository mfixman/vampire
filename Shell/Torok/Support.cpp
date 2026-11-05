#include "Support.hpp"
#include "Lib/Exception.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <numeric>
#include <random>
#include <unordered_set>

namespace {
  std::unordered_set<unsigned> selected;
}

bool Shell::Torok::supportEnabled() {
  return std::getenv("TOROK_SUPPORT") != nullptr || filterEnabled();
}

bool Shell::Torok::filterEnabled() {
  return std::getenv("TOROK_FILTER") != nullptr;
}

void Shell::Torok::filterProblem(Kernel::Problem& problem) {
  if (!filterEnabled()) {
    return;
  }

  size_t removed = 0;
  Kernel::UnitList::DelIterator units(problem.units());
  while (units.hasNext()) {
    auto unit = units.next();
    if (!unit->derivedFromGoal() && !selected.count(unit->number())) {
      units.del();
      removed += 1;
    }
  }

  if (removed) {
    problem.reportIncompleteTransformation();
    problem.invalidateByRemoval();
  }

  std::printf("%% Torok filter: removed %zu axioms\n", removed);
}

bool Shell::Torok::inSupport(Kernel::Clause* clause) {
  std::vector<Kernel::Unit*> pending{clause};
  std::unordered_set<unsigned> visited;
  while (!pending.empty()) {
    auto unit = pending.back();
    pending.pop_back();
    if (selected.count(unit->number())) {
      return true;
    }

    if (!visited.insert(unit->number()).second) {
      continue;
    }

    auto& inference = unit->inference();
    auto parents = inference.iterator();
    while (inference.hasNext(parents)) {
      pending.push_back(inference.next(parents));
    }
  }

  return false;
}

void Shell::Torok::prepareSupport(const std::vector<Kernel::Clause*>& clauses,
    const std::vector<int64_t>& axioms, const std::vector<float>& scores) {
  selected.clear();
  if (!supportEnabled()) {
    return;
  }

  char* end;
  const char* setting = std::getenv("TOROK_SUPPORT");
  if (filterEnabled()) {
    setting = std::getenv("TOROK_FILTER");
  }

  long count = std::strtol(setting, &end, 10);
  if (*end || count < 0) {
    USER_ERROR("TOROK_SUPPORT / TOROK_FILTER must be a nonnegative integer");
  }

  std::vector<size_t> order(scores.size());
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
    return scores[a] > scores[b];
  });

  if (std::getenv("TOROK_RANDOM_SUPPORT")) {
    std::mt19937 random(1);
    std::shuffle(order.begin(), order.end(), random);
  }

  for (size_t i = 0; i < std::min(order.size(), static_cast<size_t>(count)); i += 1) {
    selected.insert(clauses[axioms[order[i]]]->number());
  }

  std::printf("%% Torok ranking: selected %zu of %zu axioms\n",
      selected.size(), scores.size());
}
