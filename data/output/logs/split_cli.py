# -*- coding: utf-8 -*-
import json, os, io, re
PARSED = r"C:\Users\zhiltsov.aa\Desktop\net-auto-mermaid\data\output\logs\parsed_textfsm.json"
OUTDIR = r"data\input\cli"
os.makedirs(OUTDIR, exist_ok=True)
data = json.load(io.open(PARSED, "r", encoding="utf-8"))
hosts = data.get("hosts", {})
safe = lambda s: re.sub(r"[^0-9A-Za-z_.-]+","_", str(s)) or "host"
c = 0
for k, v in hosts.items():
    fn = os.path.join(OUTDIR, safe(k) + ".json")
    io.open(fn, "w", encoding="utf-8").write(json.dumps(v, ensure_ascii=False, indent=2))
    c += 1
print(f"[SPLIT] wrote {c} files to {OUTDIR}")
