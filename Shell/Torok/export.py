# Export the checkpoint to a tensor-only TorchScript module for LibTorch.
import argparse
import copy
import sys
from pathlib import Path
from typing import List

import torch
from torch import nn

class Features(nn.Module):
    def __init__(self, tables):
        super().__init__()
        self.tables = copy.deepcopy(tables)

    def forward(self, rows: torch.Tensor) -> torch.Tensor:
        result = self.tables[0](rows[:, 0])
        for column, table in enumerate(self.tables):
            if column > 0:
                result = result + table(rows[:, column])
        return torch.relu(result)

class Relation(nn.Module):
    __constants__ = ['src', 'dst', 'positioned']

    def __init__(self, encoder, name, src, dst, positioned):
        super().__init__()
        self.src, self.dst, self.positioned = src, dst, positioned
        self.fwd = copy.deepcopy(encoder.relation_fwd[name])
        self.rev = copy.deepcopy(encoder.relation_rev[name])

    def forward(self, h: List[torch.Tensor], incoming: List[torch.Tensor], edge: torch.Tensor, positions: torch.Tensor):
        source, target = edge[:, 0], edge[:, 1]
        left, right = h[self.src][source], h[self.dst][target]
        if self.positioned:
            pos = positions[edge[:, 2]]
            left, right = left + pos, right + pos
        incoming[self.dst] = incoming[self.dst] + self.mean(self.fwd(left), target, h[self.dst])
        incoming[self.src] = incoming[self.src] + self.mean(self.rev(right), source, h[self.src])

    def mean(self, values: torch.Tensor, index: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
        sums = torch.zeros_like(reference).index_add_(0, index, values)
        counts = torch.zeros(reference.shape[0], device = reference.device)
        counts.index_add_(0, index, torch.ones(index.shape[0], device = reference.device))
        return sums / counts.clamp(min = 1).unsqueeze(1)

class Torok(nn.Module):
    __constants__ = ['rounds']

    def __init__(self, model):
        super().__init__()
        encoder = model.encoder
        names = ['symbol', 'clause', 'literal', 'term', 'var']
        self.features = nn.ModuleList(Features(encoder.feature_embeddings[n]) for n in names)
        self.transforms = nn.ModuleList(copy.deepcopy(encoder.self_transform[n]) for n in names)
        self.norms = nn.ModuleList(copy.deepcopy(encoder.update_norm[n]) for n in names)
        relations = [('contains', 1, 2, False), ('atom', 2, 3, False),
                     ('arg_term', 3, 3, True), ('arg_var', 3, 4, True),
                     ('sym', 3, 0, False), ('lit_sym', 2, 0, False), ('complement', 2, 2, False)]
        self.relations = nn.ModuleList(Relation(encoder, *r) for r in relations)
        self.positions = copy.deepcopy(encoder.position_embedding)
        self.scorer = copy.deepcopy(model.scorer)
        self.rounds = encoder.config.message_rounds

    def forward(self, nodes: List[torch.Tensor], edges: List[torch.Tensor], axioms: torch.Tensor, conjectures: torch.Tensor) -> torch.Tensor:
        h = torch.jit.annotate(List[torch.Tensor], [])
        for i, feature in enumerate(self.features):
            h.append(feature(nodes[i]))
        for step in range(self.rounds):
            incoming = [torch.zeros_like(value) for value in h]
            for i, relation in enumerate(self.relations):
                relation(h, incoming, edges[i], self.positions.weight)
            updated = torch.jit.annotate(List[torch.Tensor], [])
            for i, transform in enumerate(self.transforms):
                updated.append(h[i] + torch.relu(transform(h[i]) + incoming[i]))
            for i, norm in enumerate(self.norms):
                h[i] = norm(updated[i])
        candidates = h[1][axioms]
        conj = h[1][conjectures].sum(0, keepdim = True) / max(conjectures.numel(), 1)
        context = candidates.sum(0, keepdim = True) / max(axioms.numel(), 1)
        conj, context = conj.expand_as(candidates), context.expand_as(candidates)
        return self.scorer(torch.cat([candidates, conj, context, candidates * conj, candidates - conj], 1)).squeeze(1)

def main():
    parser = argparse.ArgumentParser(description = 'Export a Full/ReLU Connections checkpoint for Vampire.')
    parser.add_argument('checkpoint', type = Path)
    parser.add_argument('output', type = Path)
    parser.add_argument('--connections', type = Path, required = True)
    args = parser.parse_args()
    root = args.connections.resolve()
    sys.path[:0] = [str(root / 'src'), str(root / 'packages')]
    from axiom_prediction.model import AxiomPredictor
    model = AxiomPredictor.load(args.checkpoint, device = 'cpu').model
    if str(model.config.graph_input).lower() != 'full' or str(model.config.activation).lower() != 'relu':
        raise ValueError('This exporter supports Full models with ReLU only')
    module = torch.jit.script(Torok(model).eval())
    module.save(str(args.output))
    print(f'Exported {args.output}')

if __name__ == '__main__':
    main()
