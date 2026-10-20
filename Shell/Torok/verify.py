# Check native graph construction and inference against Connections on shared CNF.
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import torch

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--connections', type = Path, required = True)
    parser.add_argument('--checkpoint', type = Path, required = True)
    parser.add_argument('--exported', type = Path, required = True)
    parser.add_argument('--checker', type = Path, required = True)
    args = parser.parse_args()
    root = args.connections.resolve()
    sys.path[:0] = [str(root / 'src'), str(root / 'packages')]
    from axiom_prediction.graph import build_axiom_graph, collate_axiom_graphs
    from axiom_prediction.model import AxiomPredictor
    from axiom_prediction.tptp import load_tptp_problem
    predictor = AxiomPredictor.load(args.checkpoint, device = 'cpu')
    torch.set_num_threads(1)
    fixtures = [
        'cnf(a,axiom,p(a)).\ncnf(g,negated_conjecture,~p(a)).',
        'cnf(a,axiom,p(X,X)|p(f(X),a)|~p(Y,f(Y))).\n'
        'cnf(b,axiom,~p(f(Z),Z)|q(f(a))).\n'
        'cnf(c,axiom,q(f(a))|r).\ncnf(g,negated_conjecture,~q(f(a))).',
        'cnf(a,axiom,p|q).\ncnf(b,axiom,~p).\ncnf(c,axiom,~q).',
        'cnf(g,negated_conjecture,~p(X)).',
        'cnf(a,axiom,a=b).\ncnf(g,negated_conjecture,a!=b).',
        'cnf(a,axiom,$false).',
    ]
    node_names = ['symbol', 'clause', 'literal', 'term', 'var']
    edge_names = ['contains', 'atom', 'arg_term', 'arg_var', 'sym', 'lit_sym', 'complement']
    with tempfile.TemporaryDirectory() as directory:
        for i, source in enumerate(fixtures):
            path = Path(directory) / f'case{i}.p'
            path.write_text(source)
            result = subprocess.run([str(args.checker), str(args.exported), str(path)],
                                    text = True, capture_output = True)
            assert result.returncode == 0, result.stderr
            native = json.loads(result.stdout)
            problem = load_tptp_problem(str(path))
            graph = build_axiom_graph(problem.matrix, axiom_clause_ids = problem.axiom_clause_ids,
                                     conjecture_clause_ids = problem.conjecture_clause_ids)
            assert native['axioms'] == graph.axiom_clause_ids
            assert native['conjectures'] == graph.conjecture_clause_ids
            for name, rows in zip(node_names, native['nodes']):
                assert rows == graph.graph.nodes[name], (i, name, rows, graph.graph.nodes[name])
            for name, rows in zip(edge_names, native['edges']):
                assert sorted(rows) == sorted(graph.graph.edges[name]), (i, name)
            batch = collate_axiom_graphs([(graph, None)])
            with torch.no_grad():
                expected = predictor.model(batch).sigmoid()
            torch.testing.assert_close(torch.tensor(native['scores']), expected, atol = 2e-5, rtol = 2e-5)
            print(f'Case {i}: graph and scores match ({len(expected)} axioms)')

if __name__ == '__main__':
    main()
