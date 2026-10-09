#!/usr/bin/env python3
"""Five-run local/two-computer matrix and CSV SHA/ratio validation."""
import argparse
import csv
from pathlib import Path
import statistics
import subprocess
import sys
import time


def verify(paths):
    groups = {}
    for path in paths:
        with open(path, encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                key = (row['environment'], Path(row['file']).name, row['mode'], row['run'])
                groups.setdefault(key, []).append(row)
    medians = {}
    assert groups, 'CSV contains no measurements'
    for key, pair in groups.items():
        assert len(pair) == 2, ('need send+recv', key)
        assert sorted(r['role'].replace('local-', '') for r in pair) == ['recv', 'send']
        assert all(r['exit_code'] == '0' and r['sha256'] for r in pair), key
        assert pair[0]['sha256'] == pair[1]['sha256'], ('SHA mismatch', key)
        assert pair[0]['wire_bytes'] == pair[1]['wire_bytes'], ('wire mismatch', key)
        for row in pair:
            size = int(row['file_bytes']); wire = int(row['wire_bytes'])
            assert abs(float(row['ratio']) - (wire / size if size else 0)) <= .000051, key
            mk = key[:3] + (row['role'],)
            medians.setdefault(mk, []).append(float(row['total_ms']))
    for key, times in sorted(medians.items()):
        assert len(times) >= 5, ('fewer than five runs', key)
        print(*key, 'runs=', len(times), 'median_total_ms=', round(statistics.median(times), 2))
    print('VERIFIED', len(groups), 'transfers; SHA, exit, wire, ratio')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['local', 'send', 'recv', 'verify'])
    ap.add_argument('files', nargs='+', help='same ordered file list on both computers; CSVs for verify')
    ap.add_argument('--ip', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=6123)
    ap.add_argument('--exe', default='./textlink.exe' if sys.platform == 'win32' else './textlink')
    ap.add_argument('--results', default='results')
    ap.add_argument('--env', default='local')
    args = ap.parse_args()
    if args.action == 'verify':
        verify(args.files); return
    for index, source in enumerate(args.files):
        name = Path(source).name
        for mode in ('raw', 'huff'):
            csvpath = Path(args.results) / f'{index:02d}_{name}_{mode}_{args.action}.csv'
            if csvpath.exists():
                sys.exit(f'Output exists; choose a fresh --results directory: {csvpath}')
            common = ['--runs', '5', '--exe', args.exe, '--env', args.env, '--csv', str(csvpath), '--' + mode]
            if args.action == 'local':
                cmd = ['local', source, '--port', str(args.port)]
            elif args.action == 'recv':
                cmd = ['recv', str(args.port), 'measure_received', '--file', name]
            else:
                cmd = ['send', args.ip, str(args.port), source]
            subprocess.run([sys.executable, str(Path(__file__).with_name('measure.py'))] + cmd + common, check=True)
            time.sleep(.5)
    print('Matrix complete. Combine send/recv CSVs and run matrix.py verify.')


if __name__ == '__main__':
    main()
