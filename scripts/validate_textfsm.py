#!/usr/bin/env python3
import sys
from pathlib import Path

def compile_template(p: Path) -> tuple[bool, str]:
    import textfsm
    try:
        with p.open('r', encoding='utf-8') as fh:
            textfsm.TextFSM(fh)
        return True, 'OK'
    except Exception as e:
        return False, str(e)

def main(argv):
    root = Path(__file__).resolve().parents[1]
    troot = root / 'templates' / 'textfsm'
    for p in sorted(troot.rglob('*.template')):
        ok, msg = compile_template(p)
        print(f"{p}: {'OK' if ok else 'ERROR'}: {msg}")

if __name__ == '__main__':
    main(sys.argv)
