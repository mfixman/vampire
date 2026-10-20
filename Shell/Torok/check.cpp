// Standalone parity check; not part of the Vampire command-line interface.
#include "Graph.hpp"
#include "Guidance.hpp"
#include "Passive.hpp"

#include "Lib/Environment.hpp"
#include "Lib/Exception.hpp"
#include "Lib/Random.hpp"
#include "Parse/TPTP.hpp"

#include <cmath>
#include <fstream>
#include <cinttypes>
#include <cstdio>
#include <iostream>
#include <stdexcept>

template<class T> void json(const std::vector<T>& values);

void json(int64_t value) { std::printf("%" PRId64, value); }

void json(float value) { std::printf("%.9g", value); }

template<class T> void json(const std::vector<T>& values) {
  std::printf("[");
  bool first = true;

  for (auto& value : values) {
    if (!first) {
      std::printf(",");
    }

    first = false;
    json(value);
  }

  std::printf("]");
}

int check(int argc, char** argv) {
  if (argc != 3) {
    return 2;
  }

  std::ifstream input(argv[2]);
  Parse::TPTP parser(input, argv[2]);
  parser.parse();
  Kernel::Problem problem(parser.units());

  std::vector<Kernel::Clause*> clauses;
  Kernel::UnitList::Iterator units(problem.units());

  while (units.hasNext()) {
    auto unit = units.next();

    if (!unit->isClause()) {
      return 3;
    }

    clauses.push_back(static_cast<Kernel::Clause*>(unit));
  }

  auto graph = Shell::Torok::buildGraph(clauses);
  auto scores = Shell::Torok::predict(graph, argv[1]);

  Lib::env.options->set("torok", argv[1]);
  Shell::Torok::prepare(problem, *Lib::env.options);

  if (clauses.size() >= 2) {
    auto a = clauses[0], b = clauses[1];
    double wa = Shell::Torok::weight(a), wb = Shell::Torok::weight(b);
    auto child = Kernel::Clause::fromLiterals({}, Kernel::GeneratingInference2(Kernel::InferenceRule::RESOLUTION, a, b));

    if (std::abs(Shell::Torok::weight(child) - std::sqrt(wa * wb)) > 1e-10) {
      throw std::runtime_error("Inherited Torok weight mismatch");
    }

    child->incRefCnt();

    Shell::Torok::Passive queue(*Lib::env.options);
    Lib::Random::setSeed(42);

    int wins = 0;
    const int samples = 10000;

    for (int i = 0; i < samples; i += 1) {
      queue.add(a);
      queue.add(b);

      wins += queue.popSelected() == a;
      queue.popSelected();
    }

    double p = wa / (wa + wb);

    if (std::abs(wins - samples * p) > 6 * std::sqrt(samples * p * (1 - p)) + 3) {
      throw std::runtime_error("Weighted Torok sampling mismatch");
    }

    queue.add(a);
    queue.add(b);
    queue.remove(a);

    if (queue.sizeEstimate() != 1 || queue.popSelected() != b || !queue.isEmpty()) {
      throw std::runtime_error("Torok removal mismatch");
    }
  }

  std::printf("{\"nodes\":[");

  for (size_t i = 0; i < graph.nodes.size(); i += 1) {
    if (i) {
      std::printf(",");
    }

    json(graph.nodes[i]);
  }

  std::printf("],\"edges\":[");

  for (size_t i = 0; i < graph.edges.size(); i += 1) {
    if (i) {
      std::printf(",");
    }

    json(graph.edges[i]);
  }

  std::printf("],\"axioms\":");
  json(graph.axioms);

  std::printf(",\"conjectures\":");
  json(graph.conjectures);

  std::printf(",\"scores\":");
  json(scores);

  std::printf("}\n");

  return 0;
}

int main(int argc, char** argv) {
  try {
    return check(argc, argv);
  } catch (Lib::Exception& error) {
    error.cry(std::cerr);
    return 1;
  } catch (std::exception& error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
  }
}
