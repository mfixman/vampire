import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import random
import shutil
import time

import local_prover9 as local

MODES = {'Prover9Late10': 10, 'Prover9Late20': 20}

def solve_late(path, tptp, predictor, budget, output, guided_seconds):
    from bounded import bounded
    from live_search import LiveSearch
    from portfolio import search
    from problem import load_problem, clause_text

    started = time.monotonic()
    deadline = started + budget
    matrix = load_problem(path, tptp)
    clauses = [clause_text(c) for c in matrix.clauses]
    remaining = lambda: max(.001, deadline - time.monotonic())
    baseline = LiveSearch(clauses, remaining(), output / 'baseline')
    result = dict(proved = False, clauses = len(clauses), support_size = 1,
                  baseline_allowance_s = budget - guided_seconds, guided_allowance_s = guided_seconds)
    try:
        initial_deadline = started + budget - guided_seconds
        found = baseline.wait(max(0, initial_deadline - time.monotonic()))
        if found and found['proved']:
            result['proved'] = True
            return result

        found = baseline.close()
        result['baseline_search'] = found
        if found and found['proved']:
            result['proved'] = True
            return result

        guided_deadline = min(deadline, time.monotonic() + guided_seconds)
        if time.monotonic() >= guided_deadline:
            return result

        def score():
            weights, info = predictor.predict(matrix)
            return dict(weights = weights, **info)

        scoring = time.monotonic()
        prediction = bounded(score, guided_deadline - scoring, output / 'prediction.json')
        result['score_s'] = time.monotonic() - scoring
        if 'error' in prediction:
            result['score_error'] = prediction['error']
            return result

        conjectures = set(matrix.conjecture_clauses)
        candidates = [i for i in range(len(clauses)) if i not in conjectures]
        ranked = sorted(candidates, key = lambda i: (-prediction['weights'][i], i))
        selected = sorted(conjectures | set(ranked[:1]))
        usable = [i for i in candidates if i not in selected]
        seconds = guided_deadline - time.monotonic()
        if seconds > 0:
            result['guided_search'] = search(clauses, selected, seconds, output / 'selected', usable = usable)
            result['proved'] = result['guided_search']['proved']

        return result
    finally:
        result['baseline_search'] = baseline.close()
        if result['baseline_search'] and result['baseline_search']['proved']:
            result['proved'] = True
        result['elapsed_s'] = time.monotonic() - started

def evaluate_bucket(cpu, problems, args):
    from bounded import bounded

    os.sched_setaffinity(0, {cpu})
    for problem in problems:
        path = Path(problem['problem'])
        target = args.output / 'groups' / f'{path.stem}.json'
        if target.exists():
            continue

        modes = list(MODES)
        random.Random(path.stem + ':late').shuffle(modes)
        result = dict(problem = str(path), sample = problem['sample'], cpu = cpu, order = modes, results = {})
        for mode in modes:
            folder = args.output / 'prover9' / path.stem / mode
            folder.mkdir(parents = True, exist_ok = True)
            completed = folder / 'result.json'
            if completed.exists():
                outcome = json.loads(completed.read_text())
            else:
                run = lambda: solve_late(path, args.tptp, local.predictor, 59.95, folder, MODES[mode])
                started = time.monotonic()
                outcome = bounded(run, 60, folder / 'bounded.json', process_group = True)
                outcome.update(elapsed_s = time.monotonic() - started, cpu = cpu)
                local.write_json(completed, outcome)

            result['results'][mode] = outcome
            print(path.stem, mode, outcome.get('proved', False), round(outcome['elapsed_s'], 2), flush = True)

        local.write_json(target, result)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous', type = Path, required = True)
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--prover9', type = Path, default = Path(__file__).resolve().parents[4] / 'Prover9')
    parser.add_argument('--tptp', type = Path, default = Path.home() / 'TP/TPTP')
    parser.add_argument('--workers', type = int, default = 18)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents = True, exist_ok = True)
    own_lock = (args.output / 'run.lock').open('w')
    fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    print('Waiting for the preceding local comparison to finish.', flush = True)
    previous_lock = (args.previous / 'run.lock').open('r')
    fcntl.flock(previous_lock, fcntl.LOCK_EX)
    previous = json.loads((args.previous / 'manifest.json').read_text())
    groups = [json.loads(p.read_text()) for p in sorted((args.previous / 'groups').glob('*.json'))]
    assert len(groups) == len(previous['problems']), 'Previous comparison is incomplete'
    for path, expected in previous['hashes'].items():
        assert local.vampire.digest(Path(path)) == expected, f'Source changed: {path}'

    cpus = sorted({g['cpu'] for g in groups})
    assert len(cpus) <= args.workers <= 18
    manifest = dict(previous = str(args.previous.resolve()), problems = previous['problems'], modes = MODES,
                    seconds = 60, cpus = cpus, hashes = previous['hashes'],
                    source_sha256 = local.vampire.digest(Path(__file__)),
                    protocol = 'Separate follow-up batch, same CPU per problem as the preceding comparison; baseline then top-1 Torok support; scoring inside final 10/20 seconds; no resumed baseline stage; warm model per worker.')
    target = args.output / 'manifest.json'
    if target.exists():
        assert json.loads(target.read_text()) == manifest, 'Resume manifest mismatch'
    else:
        local.write_json(target, manifest)
        shutil.copy2(__file__, args.output / 'prover9_late.py')

    (args.output / 'groups').mkdir(exist_ok = True)
    print(f'Starting {len(groups)} problems with {len(cpus)} workers.', flush = True)
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'),
                             initializer = local.initialize, initargs = (cpus, args.prover9, args.tptp)) as pool:
        futures = [pool.submit(evaluate_bucket, cpu, [g for g in groups if g['cpu'] == cpu], args) for cpu in cpus]
        for future in as_completed(futures):
            future.result()

    previous_lock.close()
    own_lock.close()

if __name__ == '__main__':
    main()
