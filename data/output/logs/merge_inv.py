# -*- coding: utf-8 -*-
import json, os, io, re, glob
base=r"data/input/inventory.json"
cli=r"data/input/cli"
out=r"data/input/inventory.merged.json"
devs=[]
def load(p):
    try: return json.load(io.open(p,'r',encoding='utf-8'))
    except: return {}
if os.path.exists(base): devs+=load(base).get('devices',[])
known={str(d.get('hostname') or d.get('mgmt_ip') or '').strip() for d in devs if isinstance(d,dict)}
