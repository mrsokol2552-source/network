#!/usr/bin/env python3
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stage1_collect as s

def show(dt: str):
    prof = s.merge_commands_for(dt)
    print(dt, '->', json.dumps(prof, ensure_ascii=False))

def main(argv):
    tests = argv[1:] or [
        'cisco_ios', 'cisco_xe', 'huawei', 'mikrotik_routeros', 'dlink_ds', 'qtech'
    ]
    for t in tests:
        show(t)

if __name__ == '__main__':
    main(sys.argv)
