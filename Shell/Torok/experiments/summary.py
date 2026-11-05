import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re

def sources(directory):
    if (directory / 'manifest.json').exists():
        return [directory]
    paths = sorted(p.parent for p in directory.glob('shard*/manifest.json'))
    if not paths:
        raise ValueError(f'No experiment manifests under {directory}')
    reference = json.loads((paths[0] / 'manifest.json').read_text())
    for path in paths[1:]:
        manifest = json.loads((path / 'manifest.json').read_text())
        for key in ('binary', 'model'):
            assert manifest[key] == reference[key], (path, key)
        for key in ('seconds', 'seed', 'probe', 'fraction', 'algorithm', 'extra', 'max_clauses'):
            assert manifest['settings'].get(key) == reference['settings'].get(key), (path, key)
    return paths

def read_results(directory):
    rows = defaultdict(dict)
    for source in sources(directory):
        for path in source.glob('*/*/result.json'):
            result = json.loads(path.read_text())
            name = Path(result['problem']).stem
            assert name not in rows[result['mode']], (source, name)
            rows[result['mode']][name] = result
    return rows

def summarize(directory):
    rows = read_results(directory)
    settings = json.loads((sources(directory)[0] / 'manifest.json').read_text())['settings']
    seconds = settings['seconds']
    for mode, results in sorted(rows.items()):
        solved = sum(r['solved'] for r in results.values())
        par2 = sum(r['elapsed'] if r['solved'] else 2 * seconds for r in results.values())
        print(f'{mode}: {solved}/{len(results)}, PAR2 {par2 / len(results):.3f}s')
    for base in ('baseline', 'sine', 'included', 'resume-included:4', 'resume-included:14',
                 'sinebase-resume-baseline:60'):
        if base not in rows:
            continue
        for mode in sorted(rows):
            if mode == base:
                continue
            common = rows[base].keys() & rows[mode].keys()
            gains = sorted(p for p in common if rows[mode][p]['solved'] and not rows[base][p]['solved'])
            losses = sorted(p for p in common if rows[base][p]['solved'] and not rows[mode][p]['solved'])
            baseline = sum(rows[base][p]['solved'] for p in common)
            change = 'n/a'
            if baseline:
                change = f'{100 * (len(gains) - len(losses)) / baseline:+.2f}%'
            n = len(gains) + len(losses)
            probability = min(1, 2 * sum(math.comb(n, i) for i in range(min(len(gains), len(losses)) + 1)) / 2 ** n)
            families = len(set(re.match(r'[A-Z]{3}\d{3}', p).group() for p in gains))
            print(f'{mode} vs {base}: paired={len(common)}, net={len(gains)-len(losses):+}, relative={change}, discordant p={probability:.4g}, gain families={families}')
            print('  gains:', ', '.join(gains))
            print('  losses:', ', '.join(losses))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    summarize(parser.parse_args().directory)
