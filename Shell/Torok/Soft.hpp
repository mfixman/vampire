#ifndef TOROK_SOFT_HPP
#define TOROK_SOFT_HPP

namespace Kernel { class Clause; }
namespace Shell::Torok {
  bool softEnabled();
  unsigned softWeight(const Kernel::Clause* clause, unsigned original);
}

#endif
