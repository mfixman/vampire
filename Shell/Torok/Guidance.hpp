#ifndef TOROK_GUIDANCE_HPP
#define TOROK_GUIDANCE_HPP

#include "Kernel/Problem.hpp"
#include "Shell/Options.hpp"

namespace Shell::Torok {
  void prepare(Kernel::Problem& problem, const Options& options);
  double weight(Kernel::Unit* unit);
}

#endif
