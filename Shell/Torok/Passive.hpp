#ifndef TOROK_PASSIVE_HPP
#define TOROK_PASSIVE_HPP

#include "Saturation/ClauseContainer.hpp"
#include <map>
#include <unordered_map>

namespace Shell::Torok {
  class Passive : public Saturation::PassiveClauseContainer {
    using Queue = std::map<std::pair<double, unsigned>, Kernel::Clause*>;

    Queue queue;
    std::unordered_map<Kernel::Clause*, Queue::iterator> positions;

    double clock = 0;

    public:
    explicit Passive(const Options& options)
      : PassiveClauseContainer(true, options, "Torok") {}

    ~Passive() override;

    void add(Kernel::Clause* clause) override;
    void remove(Kernel::Clause* clause) override;
    Kernel::Clause* popSelected() override;

    bool isEmpty() const override { return queue.empty(); }

    unsigned sizeEstimate() const override { return queue.size(); }

    // Weighted guidance retains clauses; there is no LRS age/weight cutoff.
    void simulationInit() override {}

    bool simulationHasNext() override { return false; }

    void simulationPopSelected() override {}

    bool setLimitsToMax() override { return false; }

    bool setLimitsFromSimulation() override { return false; }

    void onLimitsUpdated() override {}

    bool mayBeAbleToDiscriminateChildrenOnLimits() const override { return false; }

    bool allChildrenNecessarilyExceedLimits(Kernel::Clause*, unsigned) const override {
      return false;
    }

    bool mayBeAbleToDiscriminateClausesUnderConstructionOnLimits() const override {
      return false;
    }

    bool exceedsAgeLimit(unsigned, const Kernel::Inference&, bool&) const override {
      return false;
    }

    bool exceedsWeightLimit(unsigned, unsigned, const Kernel::Inference&) const override {
      return false;
    }

    bool limitsActive() const override { return false; }

    bool exceedsAllLimits(Kernel::Clause*) const override { return false; }
  };
}

#endif
