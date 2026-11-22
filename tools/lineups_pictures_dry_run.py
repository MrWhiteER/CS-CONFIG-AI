"""Fake frames only. This command never finds or writes to a CS2 install."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cs2cfg.lineups import load
from cs2cfg.lineups.pictures import dry_run

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('tmp/lineups-pictures'))
    args=parser.parse_args()
    print(dry_run(load(), 'fake-build', args.output))
