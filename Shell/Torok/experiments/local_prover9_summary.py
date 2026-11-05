import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

MODES = ['Prover9Baseline', 'Prover9ResumeSupport1', 'VampireFinal']

def summarize(rows):
    result = {'completed': len(rows), 'modes': {}, 'comparisons': {}}
    if not rows:
        return result

    for mode in MODES:
        values = [r['results'][mode] for r in rows]
        result['modes'][mode] = {
            'proofs': sum(bool(r.get('proved')) for r in values),
            'par2_s': statistics.mean(r['elapsed_s'] if r.get('proved') else 120 for r in values),
            'errors': dict(Counter(r['error'] for r in values if r.get('error') and r['error'] != 'Timeout')),
            'maximum_elapsed_s': max(r['elapsed_s'] for r in values),
        }

    for reference in [m for m in MODES if m != 'VampireFinal']:
        for mode in MODES:
            if mode == reference:
                continue

            base = {Path(r['problem']).stem for r in rows if r['results'][reference].get('proved')}
            solved = {Path(r['problem']).stem for r in rows if r['results'][mode].get('proved')}
            common = [r for r in rows if Path(r['problem']).stem in base & solved]
            result['comparisons'][f'{mode} vs {reference}'] = {
                'gains': sorted(solved - base), 'losses': sorted(base - solved),
                'relative_percent': 100 * (len(solved) - len(base)) / len(base) if base else None,
                'union': len(base | solved),
                'common_total_s': sum(r['results'][mode]['elapsed_s'] for r in common),
                'common_reference_s': sum(r['results'][reference]['elapsed_s'] for r in common),
            }

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    parser.add_argument('--late', type = Path)
    parser.add_argument('--save', action = 'store_true')
    args = parser.parse_args()
    manifest = json.loads((args.directory / 'manifest.json').read_text())
    rows = [json.loads(p.read_text()) for p in sorted((args.directory / 'groups').glob('*.json'))]
    if args.late:
        MODES.extend(['Prover9Late10', 'Prover9Late20'])
        original = {r['problem']: r for r in rows}
        rows = []
        for path in sorted((args.late / 'groups').glob('*.json')):
            late = json.loads(path.read_text())
            first = original[late['problem']]
            assert first['cpu'] == late['cpu']
            rows.append({**first, 'results': {**first['results'], **late['results']}})

    assert len({r['problem'] for r in rows}) == len(rows)
    for row in rows:
        assert set(row['results']) == set(MODES)
        assert all(r['cpu'] == row['cpu'] for r in row['results'].values())

    summary = {}
    for sample in ['development', 'heldout', 'all']:
        selected = [r for r in rows if sample == 'all' or r['sample'] == sample]
        data = summarize(selected)
        data['expected'] = sum(sample == 'all' or p['sample'] == sample for p in manifest['problems'])
        unsupported = [r for r in selected if all('Unsupported symbol' in r['results'][m].get('error', '') for m in MODES[:2])]
        data['unsupported'] = [Path(r['problem']).stem for r in unsupported]
        if unsupported:
            data['supported_only'] = summarize([r for r in selected if r not in unsupported])

        summary[sample] = data
        print(f"{sample}: {data['completed']}/{data['expected']} completed paired problems")
        for mode, values in data['modes'].items():
            print(f"  {mode}: {values['proofs']} proofs; PAR2 {values['par2_s']:.3f}s")

        if unsupported:
            print('  Unsupported by Prover9:', ', '.join(data['unsupported']))

    if args.save:
        output = args.late or args.directory
        (output / 'summary.json').write_text(json.dumps(summary, indent = 2) + '\n')

if __name__ == '__main__':
    main()
