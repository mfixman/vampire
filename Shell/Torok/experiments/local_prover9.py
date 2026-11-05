import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import random
import shutil
import sys
import time
from types import SimpleNamespace

import compare as vampire

ROOT = Path(__file__).resolve().parents[3]
SCHEDULE = 'resume-included:4+noavatar-filter16:10'
MODES = ['VampireFinal', 'Prover9Baseline', 'Prover9ResumeSupport1']
predictor = None

def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent = 2) + '\n')
    temporary.replace(path)

def initialize(cpus, prover9, tptp):
    global predictor
    identity = multiprocessing.current_process()._identity[0]
    os.sched_setaffinity(0, {cpus[(identity - 1) % len(cpus)]})
    sys.path.insert(0, str(Path(prover9) / 'axiom_selection'))
    from predict import Predictor
    from problem import load_problem

    predictor = Predictor()
    matrix = load_problem(Path(tptp) / 'Problems/GRP/GRP001-1.p', Path(tptp))
    for _ in range(3):
        predictor.predict(matrix)

def prover9_case(path, mode, args):
    from bounded import bounded
    from premise_run import Mode, solve

    folder = args.output / 'prover9' / path.stem / mode
    folder.mkdir(parents = True, exist_ok = True)
    target = folder / 'result.json'
    if target.exists():
        return json.loads(target.read_text())

    selected = Mode.Baseline if mode == 'Prover9Baseline' else Mode.ResumeSupport1
    started = time.monotonic()
    run = lambda: solve(path, args.tptp, predictor, selected, 59.95, folder, .01, 1, 16)
    result = bounded(run, 60, folder / 'bounded.json', process_group = True)
    result.update(elapsed_s = time.monotonic() - started, cpu = min(os.sched_getaffinity(0)))
    write_json(target, result)
    return result

def evaluate(problem, args):
    path = Path(problem['path'])
    target = args.output / 'groups' / f'{path.stem}.json'
    if target.exists():
        return json.loads(target.read_text())

    cpu = min(os.sched_getaffinity(0))
    modes = list(MODES)
    random.Random(path.stem).shuffle(modes)
    result = dict(problem = str(path), sample = problem['sample'], cpu = cpu, order = modes, results = {})
    settings = SimpleNamespace(output = args.output / 'vampire', tptp = args.tptp,
                               seconds = 60, probe = 45, fraction = 1 / 3, max_clauses = 256,
                               seed = 1, algorithm = 'lrs', extra = [])
    for mode in modes:
        if mode == 'VampireFinal':
            outcome = vampire.run_case(path, SCHEDULE, settings, cpu)
            outcome.update(proved = outcome['solved'], elapsed_s = outcome['elapsed'])
        else:
            outcome = prover9_case(path, mode, args)

        result['results'][mode] = outcome
        print(path.stem, mode, outcome.get('proved', False), round(outcome['elapsed_s'], 2), flush = True)

    write_json(target, result)
    return result

def input_problems():
    sources = [('development', ROOT / 'results/torok-noavatar-development/manifest.json'),
               ('heldout', ROOT / 'results/torok-sine-failure-validation.json')]
    problems = []
    for sample, source in sources:
        for path in json.loads(source.read_text())['problems']:
            problems.append(dict(path = path, sample = sample, sha256 = vampire.digest(Path(path))))

    assert len({Path(p['path']).stem for p in problems}) == len(problems)
    random.Random(20261027).shuffle(problems)
    return problems

def prepare(args, problems):
    files = [ROOT / 'build/vampire', ROOT / 'Shell/Torok/torok.ts',
             args.prover9 / 'provers.src/prover9',
             args.prover9 / 'axiom_selection/models/torok.ts']
    files += [p for p in (args.prover9 / 'axiom_selection').rglob('*.py') if 'results' not in p.parts]
    files += [args.prover9 / 'axiom_selection/build' / name for name in ['native-search', 'native-search-control']]
    files += [Path(__file__).resolve(), Path(vampire.__file__).resolve()]
    manifest = dict(problems = problems, modes = MODES, seconds = 60, schedule = SCHEDULE,
                    cpus = sorted(os.sched_getaffinity(0))[:args.workers],
                    hashes = {str(p): vampire.digest(p) for p in files},
                    protocol = 'Paired same-CPU rotated arms; Prover9 warm model per worker, Vampire cold native model; existing native memory limits retained (Prover9 512 MiB, Vampire 2048 MiB).')
    target = args.output / 'manifest.json'
    if target.exists():
        assert json.loads(target.read_text()) == manifest, 'Resume manifest mismatch'
        return manifest

    (args.output / 'vampire').mkdir()
    (args.output / 'groups').mkdir()
    shutil.copy2(files[0], args.output / 'vampire/vampire')
    shutil.copy2(files[1], args.output / 'vampire/torok.ts')
    shutil.copy2(__file__, args.output / 'local_prover9.py')
    shutil.copy2(vampire.__file__, args.output / 'compare.py')
    write_json(target, manifest)
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--prover9', type = Path, default = Path.home() / 'TP/Prover9')
    parser.add_argument('--tptp', type = Path, default = Path.home() / 'TP/TPTP')
    parser.add_argument('--workers', type = int, default = 18)
    args = parser.parse_args()
    assert 1 <= args.workers <= min(18, len(os.sched_getaffinity(0)))
    args.output = args.output.resolve()
    args.output.mkdir(parents = True, exist_ok = True)
    lock = (args.output / 'run.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    problems = input_problems()
    manifest = prepare(args, problems)
    pending = [p for p in problems if not (args.output / 'groups' / f"{Path(p['path']).stem}.json").exists()]
    print(f'{len(problems)} problems, {len(pending)} pending, {args.workers} workers', flush = True)

    with ProcessPoolExecutor(max_workers = args.workers, mp_context = multiprocessing.get_context('spawn'),
                             initializer = initialize, initargs = (manifest['cpus'], args.prover9, args.tptp)) as pool:
        futures = [pool.submit(evaluate, problem, args) for problem in pending]
        for future in as_completed(futures):
            future.result()

    lock.close()

if __name__ == '__main__':
    main()
