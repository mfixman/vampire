#ifndef TOROK_SUPPORT_HPP
#define TOROK_SUPPORT_HPP

#include "Kernel/Clause.hpp"
#include "Kernel/Problem.hpp"
#include <vector>

namespace Shell::Torok {
  bool supportEnabled();
  bool filterEnabled();
  void filterProblem(Kernel::Problem& problem);
  bool inSupport(Kernel::Clause* clause);
  void prepareSupport(const std::vector<Kernel::Clause*>& clauses,
      const std::vector<int64_t>& axioms, const std::vector<float>& scores);
}

#endif
