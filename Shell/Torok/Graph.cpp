#include "Graph.hpp"
#include "Kernel/Clause.hpp"
#include "Kernel/RobSubstitution.hpp"
#include "Lib/Exception.hpp"

#include <algorithm>
#include <map>
#include <tuple>

namespace {
  class Builder {
    Shell::Torok::Graph graph;

    std::map<std::pair<unsigned, unsigned>, int64_t> symbols;
    std::map<std::pair<unsigned, unsigned>, int64_t> variables;
    std::map<std::string, int64_t> terms;

    std::vector<Kernel::Literal*> literals;

    private:
    int64_t symbol(Kernel::Term* term, bool atom) {
      unsigned kind = 0;

      if (!atom) {
        kind = 1;

        if (!term->arity()) {
          kind = 2;
        }
      }

      auto key = std::make_pair(kind, term->functor());
      auto found = symbols.find(key);

      if (found != symbols.end()) {
        return found->second;
      }

      int64_t id = graph.nodes[0].size();
      symbols[key] = id;
      graph.nodes[0].push_back({kind, std::min(term->arity(), 4u)});

      return id;
    }

    int64_t variable(unsigned scope, unsigned var) {
      auto key = std::make_pair(scope, var);
      auto found = variables.find(key);

      if (found != variables.end()) {
        return found->second;
      }

      int64_t id = graph.nodes[4].size();
      variables[key] = id;
      graph.nodes[4].push_back({0});

      return id;
    }

    std::string termKey(Kernel::Term* term, bool atom, unsigned scope) {
      if (term->isSpecial() || term->numTypeArguments()) {
        USER_ERROR("Torok currently supports first-order terms without type arguments");
      }

      std::string key = "t";

      if (atom) {
        key = "a";
      }

      key += std::to_string(term->functor()) + "(";

      for (unsigned i = 0; i < term->arity(); i += 1) {
        auto arg = *term->nthArgument(i);

        if (arg.isVar()) {
          key += "v" + std::to_string(scope) + ":" + std::to_string(arg.var());
        } else {
          key += termKey(arg.term(), false, scope);
        }

        key += ",";
      }

      return key + ")";
    }

    int64_t intern(Kernel::Term* term, bool atom, unsigned scope) {
      auto key = termKey(term, atom, scope);
      auto found = terms.find(key);

      if (found != terms.end()) {
        return found->second;
      }

      int64_t id = graph.nodes[3].size();
      terms[key] = id;
      graph.nodes[3].push_back({term->ground()});
      graph.edges[4].push_back({id, symbol(term, atom)});

      for (unsigned i = 0; i < term->arity(); i += 1) {
        auto arg = *term->nthArgument(i);
        int64_t position = std::min(i, 5u);

        if (arg.isVar()) {
          graph.edges[3].push_back({id, variable(scope, arg.var()), position});
        } else {
          graph.edges[2].push_back({id, intern(arg.term(), false, scope), position});
        }
      }

      return id;
    }

    void complements() {
      std::map<unsigned, std::vector<int64_t>> positive, negative;

      for (size_t i = 0; i < literals.size(); i += 1) {
        if (literals[i]->polarity()) {
          positive[literals[i]->functor()].push_back(i);
        } else {
          negative[literals[i]->functor()].push_back(i);
        }
      }

      Kernel::RobSubstitution substitution;

      for (auto& [predicate, lefts] : positive) {
        for (auto left : lefts) {
          for (auto right : negative[predicate]) {
            auto a = literals[left], b = literals[right];
            bool unifies = a->arity() == b->arity();
            substitution.reset();

            for (unsigned i = 0; unifies && i < a->arity(); i += 1) {
              unifies = substitution.unify(*a->nthArgument(i), 0, *b->nthArgument(i), 1);
            }

            if (unifies) {
              graph.edges[6].push_back({left, right});
              graph.edges[6].push_back({right, left});
            }
          }
        }
      }

      std::sort(graph.edges[6].begin(), graph.edges[6].end());
    }

    public:
    Shell::Torok::Graph build(const std::vector<Kernel::Clause*>& clauses) {
      for (size_t i = 0; i < clauses.size(); i += 1) {
        auto clause = clauses[i];
        bool goal = clause->derivedFromGoal();

        if (goal) {
          graph.conjectures.push_back(i);
        } else {
          graph.axioms.push_back(i);
        }

        unsigned sizeBucket = 0;

        if (clause->length()) {
          sizeBucket = std::min(clause->length() - 1, 4u);
        }

        graph.nodes[1].push_back({sizeBucket, goal, clause->isGround(), goal});

        for (unsigned j = 0; j < clause->length(); j += 1) {
          auto literal = (*clause)[j];
          int64_t id = literals.size();

          literals.push_back(literal);
          graph.nodes[2].push_back({literal->polarity()});

          graph.edges[0].push_back({static_cast<int64_t>(i), id});
          graph.edges[1].push_back({id, intern(literal, true, i)});
          graph.edges[5].push_back({id, symbol(literal, true)});
        }
      }

      complements();

      return std::move(graph);
    }
  };
}

Shell::Torok::Graph Shell::Torok::buildGraph(const std::vector<Kernel::Clause*>& clauses) {
  return Builder().build(clauses);
}
