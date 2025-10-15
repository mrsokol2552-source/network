#!/usr/bin/env python3
from pathlib import Path

def strip_bom(path: Path) -> bool:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(data[3:])
        return True
    return False

def main():
    root = Path('templates/textfsm')
    changed = 0
    for p in list(root.rglob('*.template')) + list(root.rglob('example.txt')):
        if strip_bom(p):
            print('BOM removed:', p)
            changed += 1
    print('Done, changed:', changed)

if __name__ == '__main__':
    main()
