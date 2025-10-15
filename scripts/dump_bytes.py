#!/usr/bin/env python3
from pathlib import Path
def main():
    for p in sorted((Path('templates/textfsm/cisco_ios')).glob('*.template')):
        b = p.read_bytes()[:8]
        print(p.name, list(b))
if __name__ == '__main__':
    main()
