"""One local/CI release gate. All app data is isolated for the entire run."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser',action='store_true',help='Require Node and Chrome browser checks too')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cs2cfg-verify-') as data:
        data = str(Path(data).resolve())
        env = dict(os.environ, CS2CFG_DATA=data, PYTHONUTF8='1',
                   TEMP=data, TMP=data, TMPDIR=data,
                   CS2CFG_TEST_PREVIEWS=str(Path(data) / 'browser-previews'))
        commands=[[sys.executable,'-m','unittest','discover','-s','tests']]
        if args.browser:
            node=shutil.which('node')
            if not node:
                parser.error('Node is required for --browser')
            checks=sorted(p for p in (ROOT/'tools').glob('check_*.cjs') if p.name!='check_faceit_dashboard.cjs')
            commands.extend([node,str(p)] for p in checks)
            commands.extend([[node,'tools/lineups_preview.cjs','--check'],[node,'tools/overlay_preview.cjs','--check']])
        failures = []
        for command in commands:
            print('\nRunning: '+' '.join(command),flush=True)
            result=subprocess.run(command,cwd=ROOT,env=env)
            if result.returncode:
                failures.append((' '.join(command), result.returncode))
        if failures:
            for command, code in failures:
                print(f'Failed ({code}): {command}')
            return 1
    print('\nAll required verification checks passed.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
