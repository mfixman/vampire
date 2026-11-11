import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_tptp import part

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def problems(args):
    if args.manifest:
        data = json.loads(args.manifest.read_text())
        return [Path(p) for p in data['problems']]

    paths = sorted((args.tptp / 'Problems').rglob('*.p'))
    paths = [p for p in paths if part(p, args.split) in args.part]
    paths = [p for p in paths if '-' in p.stem or '+' in p.stem]
    return [p for p in paths if re.search(
        r'% Status\s*:\s*(Theorem|Unsatisfiable|ContradictoryAxioms)\s*\n',
        p.read_text(errors = 'replace')[:10000])]

def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()

def launch(problem, mode, args, cpu, log, limit = None, pause_clock = False):
    env = dict(os.environ, TPTP = str(args.tptp), OMP_NUM_THREADS = '1',
               OPENBLAS_NUM_THREADS = '1', MKL_NUM_THREADS = '1')
    env.pop('TOROK_SUPPORT', None)
    env.pop('TOROK_FILTER', None)
    env.pop('TOROK_SOFT', None)
    env.pop('TOROK_ACTIVE_LRS', None)
    env.pop('TOROK_MAX_CLAUSES', None)
    env.pop('TOROK_RANDOM_SUPPORT', None)
    if pause_clock:
        env['TOROK_ACTIVE_LRS'] = '1'
    if args.max_clauses:
        env['TOROK_MAX_CLAUSES'] = str(args.max_clauses)
    limit = args.seconds if limit is None else max(0.1, limit)
    command = ['taskset', '-c', str(cpu), str(args.output / 'vampire'),
               '--mode', 'vampire', '--time_limit', f'{limit:.1f}s',
               '--memory_limit', str(args.memory_mb), '--random_seed', str(args.seed),
               '--proof', 'tptp', '--saturation_algorithm', args.algorithm,
               '--sine_selection', 'included' if 'included' in mode else 'axioms' if 'sine' in mode else 'off']
    if 'support' in mode or 'filter' in mode or 'soft' in mode or mode == 'weighted':
        command += ['--torok_file', str(args.output / 'torok.ts')]
    if 'support' in mode:
        size = re.search(r'support(\d+)', mode).group(1)
        env['TOROK_SUPPORT'] = size
        command += ['--sos', 'on' if 'soson' in mode else 'all']
    if 'filter' in mode:
        env['TOROK_FILTER'] = re.search(r'filter(\d+)', mode).group(1)
    if 'soft' in mode:
        env['TOROK_SOFT'] = re.search(r'soft(\d+)', mode).group(1)
    if 'random' in mode:
        env['TOROK_RANDOM_SUPPORT'] = '1'
    if mode.endswith('sos'):
        command += ['--sos', 'all']
    if mode.endswith('soson') and 'support' not in mode:
        command += ['--sos', 'on']
    if 'noavatar' in mode:
        command += ['--avatar', 'off']
    command += args.extra + [str(problem)]
    return subprocess.Popen(command, stdout = log, stderr = subprocess.STDOUT,
                            env = env, start_new_session = True)

def wait_until(process, deadline):
    try:
        process.wait(timeout = max(0, deadline - time.monotonic()))
        return True
    except subprocess.TimeoutExpired:
        return False

def proved(path):
    return bool(re.search(r'SZS status (Theorem|Unsatisfiable|ContradictoryAxioms)\b',
                          path.read_text(errors = 'replace')))

def guided_search(problem, mode, args, cpu, folder, deadline, logs, processes, stages, started):
    alternatives = mode.split('+')
    allowance = args.seconds * args.fraction / len(alternatives)
    for index, alternative in enumerate(alternatives):
        if time.monotonic() >= deadline:
            break
        name = 'guided.log' if len(alternatives) == 1 else f'guided-{index}.log'
        path = folder / name
        logs.append(path)
        strategy, separator, seconds = alternative.partition(':')
        duration = float(seconds) if separator else allowance
        if duration <= 0:
            raise ValueError('Guided slice durations must be positive')
        with path.open('w') as output:
            limit = min(duration, deadline - time.monotonic())
            process = launch(problem, strategy, args, cpu, output, limit = limit)
            processes.append(process)
            wait_until(process, min(deadline, time.monotonic() + duration))
            stop(process)
        stages.append(dict(stage = alternative, elapsed = time.monotonic() - started))
        if proved(path):
            return True
    return False

def run_case(problem, mode, args, cpu):
    folder = args.output / problem.stem / mode
    folder.mkdir(parents = True, exist_ok = True)
    result_path = folder / 'result.json'
    if result_path.exists():
        return json.loads(result_path.read_text())
    started = time.monotonic()
    deadline = started + args.seconds
    processes = []
    logs = []
    stages = []
    try:
        base = 'included' if mode.startswith('included-') else 'sine' if mode.startswith('sine-') else 'baseline'
        guided_mode = mode
        if mode.startswith('sinebase-'):
            base = 'included'
            guided_mode = mode.removeprefix('sinebase-')
        first = base if 'resume' in mode else mode
        path = folder / 'first.log'
        logs.append(path)
        with path.open('w') as output:
            process = launch(problem, first, args, cpu, output, pause_clock = 'resume' in mode)
            processes.append(process)
            if 'resume' not in mode:
                wait_until(process, deadline)
            else:
                done = wait_until(process, min(deadline, started + args.probe))
                stages.append({'stage': 'probe', 'elapsed': time.monotonic() - started})
                if not (done and proved(path)):
                    if not done:
                        os.killpg(process.pid, signal.SIGSTOP)
                    success = guided_search(problem, guided_mode, args, cpu, folder, deadline,
                                            logs, processes, stages, started)
                    if not success and not done:
                        os.killpg(process.pid, signal.SIGCONT)
                        wait_until(process, deadline)
    finally:
        for process in processes:
            stop(process)
    elapsed = time.monotonic() - started
    texts = [p.read_text(errors = 'replace') for p in logs]
    result = dict(problem = str(problem), mode = mode, solved = any(proved(p) for p in logs),
                  elapsed = elapsed, stages = stages, cpu = cpu,
                  statuses = re.findall(r'SZS status (\w+)', '\n'.join(texts)),
                  exit_codes = [p.returncode for p in processes],
                  reasons = re.findall(r'Termination reason: ([^\n]+)', '\n'.join(texts)),
                  proof_logs = [p.name for p in logs if proved(p)],
                  score_errors = re.findall(r'Torok inference failed: ([^\n]+)', '\n'.join(texts)))
    temporary = result_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent = 2) + '\n')
    temporary.replace(result_path)
    return result

def execute_group(problem, args, cpus):
    cpu = cpus.get()
    try:
        offset = int(hashlib.md5(problem.stem.encode()).hexdigest(), 16) % len(args.modes)
        modes = args.modes[offset:] + args.modes[:offset]
        for mode in modes:
            result = run_case(problem, mode, args, cpu)
            print(f"{problem.stem} {mode} {result['solved']} {result['elapsed']:.2f}", flush = True)
    finally:
        cpus.put(cpu)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tptp', type = Path, default = Path.home() / 'TP/TPTP')
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--manifest', type = Path)
    parser.add_argument('--model', type = Path, default = ROOT / 'Shell/Torok/torok.ts')
    parser.add_argument('--split', type = int, default = 100)
    parser.add_argument('--part', type = int, nargs = '+', default = [0])
    parser.add_argument('--workers', type = int, default = 18)
    parser.add_argument('--seconds', type = float, default = 60)
    parser.add_argument('--seed', type = int, default = 1)
    parser.add_argument('--probe', type = float, default = 1)
    parser.add_argument('--fraction', type = float, default = 1 / 3)
    parser.add_argument('--max-clauses', type = int, default = 0)
    parser.add_argument('--memory-mb', type = int, default = 3072)
    parser.add_argument('--algorithm', default = 'otter')
    parser.add_argument('--modes', nargs = '+', default = ['baseline', 'sine', 'resume-support1'])
    parser.add_argument('--extra', nargs = '*', default = [])
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents = True, exist_ok = True)
    paths = problems(args)
    manifest = dict(problems = list(map(str, paths)), settings = {
        k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        binary = digest(ROOT / 'build/vampire'), model = digest(args.model),
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd = ROOT, text = True).strip())
    target = args.output / 'manifest.json'
    if target.exists():
        old = json.loads(target.read_text())
        for key in ('problems', 'binary', 'model', 'settings'):
            if old[key] != manifest[key]:
                raise ValueError(f'Resume mismatch: {key}')
    else:
        target.write_text(json.dumps(manifest, indent = 2) + '\n')
        shutil.copy2(ROOT / 'build/vampire', args.output / 'vampire')
        shutil.copy2(args.model, args.output / 'torok.ts')
        shutil.copy2(__file__, args.output / 'compare.py')
        patch = subprocess.check_output(['git', 'diff'], cwd = ROOT)
        (args.output / 'source.patch').write_bytes(patch)
        shutil.copytree(ROOT / 'Shell/Torok', args.output / 'source',
                        ignore = shutil.ignore_patterns('torok.ts', '__pycache__'))
    cpus = queue.Queue()
    for cpu in sorted(os.sched_getaffinity(0))[:args.workers]:
        cpus.put(cpu)
    print(f'{len(paths)} problems, {args.modes}, {cpus.qsize()} workers', flush = True)
    with concurrent.futures.ThreadPoolExecutor(max_workers = cpus.qsize()) as pool:
        futures = [pool.submit(execute_group, p, args, cpus) for p in paths]
        for future in concurrent.futures.as_completed(futures):
            future.result()

if __name__ == '__main__':
    main()
