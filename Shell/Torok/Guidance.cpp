#include "Guidance.hpp"
#include "Graph.hpp"
#include "Kernel/Clause.hpp"
#include "Shell/Property.hpp"
#include "Lib/Exception.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include <unordered_map>

namespace {
  std::unordered_map<unsigned, double> logWeights;
  double neutralLogWeight = 0;
}

void Shell::Torok::prepare(Kernel::Problem& problem, const Options& options) {
  problem.getProperty();

  const auto unsupported = {
    &Kernel::Problem::mayHaveFormulas,
    &Kernel::Problem::isHigherOrder,
    &Kernel::Problem::hasFOOL,
    &Kernel::Problem::hasInterpretedOperations,
    &Kernel::Problem::hasNonDefaultSorts
  };

  for (auto check : unsupported) {
    if ((problem.*check)()) {
      USER_ERROR("Torok currently supports clausified untyped first-order problems without interpreted operations");
    }
  }

  auto started = std::chrono::steady_clock::now();

  std::vector<Kernel::Clause*> clauses;
  Kernel::UnitList::Iterator units(problem.units());

  while (units.hasNext()) {
    clauses.push_back(static_cast<Kernel::Clause*>(units.next()));
  }

  auto graph = buildGraph(clauses);
  std::vector<float> scores;

  try {
    scores = predict(graph, options.torok());
  } catch (const std::exception& error) {
    USER_ERROR(error.what());
  }

  logWeights.clear();
  neutralLogWeight = 0;

  for (size_t i = 0; i < scores.size(); i += 1) {
    double value = std::log(std::max(1e-6, static_cast<double>(scores[i])));
    logWeights[clauses[graph.axioms[i]]->number()] = value;
    neutralLogWeight += value;
  }

  for (auto i : graph.conjectures) {
    logWeights[clauses[i]->number()] = 0;
  }

  // Connections includes the conjecture's unit weights when computing the neutral weight.
  if (!clauses.empty()) {
    neutralLogWeight /= clauses.size();
  }

  auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();

  if (options.showPreprocessing()) {
    std::printf(
      "%% Torok: scored %zu axioms, retained all %zu clauses; graph and inference %g s\n",
      scores.size(),
      clauses.size(),
      elapsed
    );
  }
}

double Shell::Torok::weight(Kernel::Unit* unit) {
  std::vector<std::pair<Kernel::Unit*, bool>> pending{{unit, false}};

  while (!pending.empty()) {
    auto [current, visited] = pending.back();
    pending.pop_back();

    if (logWeights.count(current->number())) {
      continue;
    }

    auto& inference = current->inference();
    auto parents = inference.iterator();

    if (!visited) {
      pending.push_back({current, true});

      while (inference.hasNext(parents)) {
        auto parent = inference.next(parents);

        if (!logWeights.count(parent->number())) {
          pending.push_back({parent, false});
        }
      }
    } else {
      double sum = 0;
      size_t count = 0;

      while (inference.hasNext(parents)) {
        sum += logWeights.at(inference.next(parents)->number());
        count += 1;
      }

      double value = neutralLogWeight;

      if (count) {
        value = sum / count;
      }

      logWeights[current->number()] = value;
    }
  }

  return std::exp(logWeights.at(unit->number()));
}
