#include "Graph.hpp"
#include <stdexcept>

#include <torch/script.h>
#include <ATen/Parallel.h>
#include <map>
#include <memory>

namespace {
  torch::Tensor tensor(const Shell::Torok::Rows& rows, int64_t width) {
    std::vector<int64_t> flat;
    flat.reserve(rows.size() * width);

    for (auto& row : rows) {
      flat.insert(flat.end(), row.begin(), row.end());
    }

    return torch::tensor(flat, torch::kInt64).reshape({static_cast<int64_t>(rows.size()), width});
  }
}

std::vector<float> Shell::Torok::predict(const Graph& graph, const std::string& modelPath) {
  try {
    static std::map<std::string, torch::jit::Module> models;

    at::set_num_threads(1);
    torch::NoGradGuard guard;

    auto found = models.find(modelPath);

    if (found == models.end()) {
      auto model = torch::jit::load(modelPath, torch::kCPU);
      model.eval();
      found = models.emplace(modelPath, std::move(model)).first;
    }

    c10::List<torch::Tensor> nodes, edges;

    const int nodeWidths[] = {2, 4, 1, 1, 1};
    const int edgeWidths[] = {2, 2, 3, 3, 2, 2, 2};

    for (size_t i = 0; i < graph.nodes.size(); i += 1) {
      nodes.push_back(tensor(graph.nodes[i], nodeWidths[i]));
    }

    for (size_t i = 0; i < graph.edges.size(); i += 1) {
      edges.push_back(tensor(graph.edges[i], edgeWidths[i]));
    }

    auto output = found->second.forward({
      nodes,
      edges,
      torch::tensor(graph.axioms, torch::kInt64),
      torch::tensor(graph.conjectures, torch::kInt64)
    }).toTensor();

    if (output.dim() != 1 || output.numel() != static_cast<int64_t>(graph.axioms.size()) ||
        !torch::isfinite(output).all().item<bool>()) {
      throw std::runtime_error("Torok returned invalid scores");
    }

    auto probabilities = output.sigmoid().contiguous();
    auto data = probabilities.data_ptr<float>();

    return {data, data + probabilities.numel()};
  } catch (const c10::Error& error) {
    throw std::runtime_error(std::string("Torok inference failed: ") + error.what_without_backtrace());
  }
}
