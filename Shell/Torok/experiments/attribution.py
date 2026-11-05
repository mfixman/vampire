import argparse
from collections import Counter
from pathlib import Path
from summary import read_results

def proof_stage(result):
    if 'first.log' in result['proof_logs']:
        if 'resume' in result['mode']:
            return 'initial search'

        return result['mode']

    log = result['proof_logs'][0]
    index = 0
    if log != 'guided.log':
        index = int(log.removeprefix('guided-').removesuffix('.log'))

    stages = [s['stage'] for s in result['stages'] if s['stage'] != 'probe']
    return stages[index].split(':')[0].removeprefix('resume-')

def report(directory, reference):
    rows = read_results(directory)
    baseline = rows[reference]
    for mode, results in sorted(rows.items()):
        if mode == reference:
            continue

        gains = sorted(
            name for name in results.keys() & baseline.keys()
            if results[name]['solved'] and not baseline[name]['solved']
        )
        stages = Counter(proof_stage(results[name]) for name in gains)
        print(f'{mode}: {len(gains)} gains over {reference}; {dict(stages)}')
        for name in gains:
            result = results[name]
            print(f"  {name}: {proof_stage(result)}, {result['elapsed']:.2f}s")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    parser.add_argument('--reference', default = 'included')
    args = parser.parse_args()
    report(args.directory, args.reference)
