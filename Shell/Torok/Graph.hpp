#ifndef TOROK_GRAPH_HPP
#define TOROK_GRAPH_HPP

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace Kernel {
  class Clause;
}

namespace Shell::Torok {
  using Rows = std::vector<std::vector<int64_t>>;

  struct Graph {
    std::array<Rows, 5> nodes;
    std::array<Rows, 7> edges;

    std::vector<int64_t> axioms;
    std::vector<int64_t> conjectures;
  };

  Graph buildGraph(const std::vector<Kernel::Clause*>& clauses);
  std::vector<float> predict(const Graph& graph, const std::string& modelPath);
}

#endif
