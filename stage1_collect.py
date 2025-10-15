#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Р­РўРђРџ 1: РЎР‘РћР  Р’Р«Р’РћР”РћР’ РљРћРњРђРќР” РЎ РЈРЎРўР РћР™РЎРўР’ (Р‘Р•Р— РРќР’Р•РќРўРђР РЇ)

Р§С‚Рѕ РґРµР»Р°РµС‚ СЌС‚РѕС‚ СЃРєСЂРёРїС‚:
  вЂў РџСЂРёРЅРёРјР°РµС‚ С†РµР»Рё РІ РґРІСѓС… С„РѕСЂРјР°С…:
      --targets  IP/РёРјРµРЅР° С‡РµСЂРµР· РїСЂРѕР±РµР»
      --cidr     РїРѕРґСЃРµС‚Рё РІ С„РѕСЂРјР°С‚Рµ CIDR (РЅР°РїСЂРёРјРµСЂ, 10.20.96.0/24)
    Р•СЃР»Рё СѓРєР°Р·Р°РЅС‹ РѕР±Р° РІР°СЂРёР°РЅС‚Р° вЂ” РѕР±СЉРµРґРёРЅСЏРµРј.
  вЂў РџРѕРґРєР»СЋС‡Р°РµС‚СЃСЏ Рє РєР°Р¶РґРѕРјСѓ Р°РґСЂРµСЃСѓ РїРѕ SSH; РїСЂРё РЅРµСѓСЃРїРµС…Рµ вЂ” РїСЂРѕР±СѓРµС‚ Telnet.
  вЂў Р”Р»СЏ РєР°Р¶РґРѕРіРѕ СѓСЃРїРµС€РЅРѕРіРѕ С…РѕСЃС‚Р° РІС‹РїРѕР»РЅСЏРµС‚ РЅР°Р±РѕСЂ В«РґРёР°РіРЅРѕСЃС‚РёС‡РµСЃРєРёС…В» РєРѕРјР°РЅРґ
    (РїРѕРґ СЂР°Р·РЅС‹Рµ РІРµРЅРґРѕСЂС‹) Рё СЃРѕС…СЂР°РЅСЏРµС‚ РІСЃРµ РІС‹РІРѕРґС‹ РІ РѕРґРёРЅ С„Р°Р№Р»:
      data/raw/<IP>.txt
  вЂў РљР°Р¶РґР°СЏ РєРѕРјР°РЅРґР° РІ С„Р°Р№Р»Рµ РїРѕРјРµС‡Р°РµС‚СЃСЏ РєР°Рє:
      $ <РєРѕРјР°РЅРґР°>
      <СЃС‹СЂРѕР№ РІС‹РІРѕРґ>
    Р­С‚Рѕ СѓРїСЂРѕСЃС‚РёС‚ РїРѕСЃР»РµРґСѓСЋС‰РёР№ РїР°СЂСЃРёРЅРі.

Р—Р°С‡РµРј СЃС‚РѕР»СЊРєРѕ РєРѕРјРјРµРЅС‚Р°СЂРёРµРІ:
  вЂў РЎРµР№С‡Р°СЃ РЅР°С€Р° С†РµР»СЊ вЂ” СЃРґРµР»Р°С‚СЊ РѕСЃРЅРѕРІСѓ РјР°РєСЃРёРјР°Р»СЊРЅРѕ РїСЂРѕР·СЂР°С‡РЅРѕР№,
    С‡С‚РѕР±С‹ РІ Р»СЋР±РѕР№ РјРѕРјРµРЅС‚ РјРѕР¶РЅРѕ Р±С‹Р»Рѕ:
      - Р±С‹СЃС‚СЂРѕ РґРѕР±Р°РІРёС‚СЊ РЅРѕРІС‹Р№ РІРµРЅРґРѕСЂ/С‚РёРї,
      - РїРѕРјРµРЅСЏС‚СЊ РїРµСЂРµС‡РµРЅСЊ РєРѕРјР°РЅРґ,
      - СЂР°СЃС€РёСЂРёС‚СЊ Р»РѕРіРё/РѕР±СЂР°Р±РѕС‚РєСѓ РѕС€РёР±РѕРє,
      - РёРЅС‚РµРіСЂРёСЂРѕРІР°С‚СЊ ntc-templates/TextFSM РЅР° СЃР»РµРґСѓСЋС‰РµРј СЌС‚Р°РїРµ.

РўСЂРµР±РѕРІР°РЅРёСЏ Рє РѕРєСЂСѓР¶РµРЅРёСЋ:
  вЂў Python 3.9+
  вЂў pip install netmiko paramiko rich tqdm
  вЂў РџРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ (РЅРµРѕР±СЏР·Р°С‚РµР»СЊРЅРѕ, РјРѕР¶РЅРѕ РІРІРµСЃС‚Рё СЂСѓРєР°РјРё РїСЂРё СЃС‚Р°СЂС‚Рµ):
      NET_USER, NET_PASS, NET_ENABLE
  вЂў Р—Р°РїСѓСЃРє РїСЂРёРјРµСЂРѕРІ:
      python stage1_collect.py --cidr 10.20.96.0/24 10.20.97.0/24
      python stage1_collect.py --targets 10.20.96.10 10.20.96.11

Р’Р°Р¶РЅРѕ:
  вЂў Р’ СЂР°РјРєР°С… РїРµСЂРІРѕР№ РІРµСЂСЃРёРё РјС‹ РќР• РёСЃРїРѕР»СЊР·СѓРµРј РІРЅРµС€РЅРёР№ РёРЅРІРµРЅС‚Р°СЂРЅС‹Р№ С„Р°Р№Р».
    Р’СЃС‘ РјРёРЅРёРјР°Р»СЊРЅРѕ: С†РµР»Рё РїСЂРёС…РѕРґСЏС‚ РёР· CLI РїР°СЂР°РјРµС‚СЂРѕРІ.
  вЂў РњС‹ СѓРјС‹С€Р»РµРЅРЅРѕ СЃРѕС…СЂР°РЅСЏРµРј СЃС‹СЂС‹Рµ РІС‹РІРѕРґС‹ Р±РµР· СЃС‚СЂСѓРєС‚СѓСЂРёСЂРѕРІР°РЅРёСЏ вЂ” СЌС‚Рѕ РѕСЃРѕР·РЅР°РЅРЅС‹Р№
    РІС‹Р±РѕСЂ, С‚.Рє. Р­С‚Р°Рї 2 Р·Р°Р№РјС‘С‚СЃСЏ РїР°СЂСЃРёРЅРіРѕРј (РІ С‚.С‡. С‡РµСЂРµР· TextFSM/ntc-templates).
"""

from __future__ import annotations

import argparse
import json
import getpass
import ipaddress
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import socket
import time
# Р’РЅРµС€РЅСЏСЏ Р·Р°РІРёСЃРёРјРѕСЃС‚СЊ: netmiko вЂ” Р±РёР±Р»РёРѕС‚РµРєР° РґР»СЏ SSH/Telnet РЅР° СЃРµС‚РµРІС‹Рµ СѓСЃС‚СЂРѕР№СЃС‚РІР°
# Р”РѕРєСѓРјРµРЅС‚Р°С†РёСЏ: https://github.com/ktbyers/netmiko
from netmiko import ConnectHandler
try:  # SSH autodetect (best-effort)
    from netmiko.ssh_autodetect import SSHDetect  # type: ignore
except Exception:  # pragma: no cover
    SSHDetect = None  # fallback without autodetect
def is_port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

# -----------------------
# РќРђРЎРўР РћР™РљР Р РљРћРќРЎРўРђРќРўР«
# -----------------------

# РџР°РїРєР°, РєСѓРґР° РїРёС€РµРј СЃС‹СЂС‹Рµ РІС‹РІРѕРґС‹
DATA_RAW = Path("data") / "raw"
COLLECT_CFG_DIR = Path("config") / "collect"

# РџРµСЂРµС‡РµРЅСЊ РєРѕРјР°РЅРґ РїРѕРґ СЂР°Р·РЅС‹Рµ device_type.
# РџСЂРёРјРµС‡Р°РЅРёСЏ:
#  - РєР»СЋС‡Рё СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‚ С‚РёРїР°Рј Netmiko (РЅР°РїСЂРёРјРµСЂ, "cisco_ios", "cisco_ios_telnet")
#  - РµСЃР»Рё РЅСѓР¶РЅРѕРіРѕ РєР»СЋС‡Р° РЅРµС‚, РёСЃРїРѕР»СЊР·СѓРµРј "generic"
#  - "pre_enable": РµСЃР»Рё True вЂ” РїС‹С‚Р°РµРјСЃСЏ РІС‹РїРѕР»РЅРёС‚СЊ enable() РїРѕСЃР»Рµ РІС…РѕРґР°
COMMANDS_BY_TYPE: Dict[str, Dict] = {
    "cisco_ios": {
        "pre_enable": True,
        "commands": [
            "show running-config",
            "show version",
            # CDP/LLDP вЂ” РґР»СЏ С‚РѕРїРѕР»РѕРіРёРё (Р­С‚Р°Рї 2 Р±СѓРґРµС‚ РІС‹С‚СЏРіРёРІР°С‚СЊ СЃРѕСЃРµРґРµР№)
            "show cdp neighbors detail",
            "show lldp neighbors detail",
            # РџРѕСЂС‚С‹ (СЃС‚Р°С‚СѓСЃ/VLAN) вЂ” РїСЂРёРіРѕРґРёС‚СЃСЏ РґР»СЏ РїРѕРґРїРёСЃРµР№ Рё С„РёР»СЊС‚СЂР°С†РёРё
            "show interface status",
        ],
    },
    # Р”Р»СЏ Telnet-СѓСЃС‚СЂРѕР№СЃС‚РІ Cisco Netmiko РѕР¶РёРґР°РµС‚ РѕС‚РґРµР»СЊРЅС‹Р№ С‚РёРї:
    "cisco_ios_telnet": {"extends": "cisco_ios"},
    # HP ProCurve / ArubaOS-Switch
    "hp_procurve": {
        "pre_enable": False,
        "commands": [
            "show running-config",
            "show system-information",
            # LLDP (Сѓ ProCurve РґСЂСѓРіРѕР№ СЃРёРЅС‚Р°РєСЃРёСЃ)
            "show lldp info remote-device detail",
            # РЎРІРѕРґРєР° РїРѕ РёРЅС‚РµСЂС„РµР№СЃР°Рј
            "show interfaces brief",
        ],
    },
    # РРЅРѕРіРґР° РґР»СЏ Telnet РїРѕРґ ProCurve РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ С‚РѕС‚ Р¶Рµ С‚РёРї СЃ СЃСѓС„С„РёРєСЃРѕРј,
    # РЅРѕ РЅРµ РІРѕ РІСЃРµС… РІРµСЂСЃРёСЏС… Netmiko РµСЃС‚СЊ СЏРІРЅС‹Р№ *_telnet. РћСЃС‚Р°РІРёРј РјР°РїРїРёРЅРі РЅР° Р±СѓРґСѓС‰РµРµ.
    "hp_procurve_telnet": {"extends": "hp_procurve"},
    # Juniper JunOS вЂ” РєРѕРјР°РЅРґС‹ РІРёРґР° "show ...", РєРѕРЅС„РёРіРё СѓРґРѕР±РЅРѕ РІ display set
    "juniper_junos": {
        "pre_enable": False,
        "commands": [
            "show configuration | display set",
            "show version",
            "show lldp neighbors detail",
            "show interfaces terse",
            "show chassis hardware",
        ],
    },
    "juniper_junos_telnet": {"extends": "juniper_junos"},
    # Generic вЂ” РЅР° СЃР»СѓС‡Р°Р№ В«С‡РµРіРѕ-С‚Рѕ РЅРµРёР·РІРµСЃС‚РЅРѕРіРѕВ», Р»СѓС‡С€Рµ С‡РµРј РЅРёС‡РµРіРѕ
    "generic": {
        "pre_enable": False,
        "commands": [
            "show running-config",
            "show lldp neighbors detail",
        ],
    },
    "generic_telnet": {"extends": "generic"},
}

# Optional mapping from Netmiko autodetected device types to our profiles
NETMIKO_TO_PROFILE = {
    "cisco_ios": "cisco_ios",
    "hp_procurve": "hp_procurve",
    "aruba_procurve": "hp_procurve",
    "juniper_junos": "juniper_junos",
    "juniper": "juniper_junos",
    "mikrotik_routeros": "generic",  # TODO: add dedicated profile if needed
    "huawei": "generic",
    "dlink_ds": "generic",
}

# РџРѕСЂСЏРґРѕРє РїРѕРїС‹С‚РѕРє: СЃРЅР°С‡Р°Р»Р° SSH, Р·Р°С‚РµРј Telnet, РїРѕ РІРµРЅРґРѕСЂР°Рј
# Р’ СЂРµР°Р»СЊРЅРѕСЃС‚Рё РІС‹ РјРѕР¶РµС‚Рµ РѕРіСЂР°РЅРёС‡РёС‚СЊ СЃРїРёСЃРѕРє РїРѕРґ СЃРІРѕР№ Р·РѕРѕРїР°СЂРє СѓСЃС‚СЂРѕР№СЃС‚РІ.
DEVICE_TRY_ORDER = [
    "cisco_ios",
    "hp_procurve",
    "juniper_junos",
    "generic",
]

console = Console()


# ---------------
# Р’РЎРџРћРњРћР“РђРўР•Р›Р¬РќРћР•
# ---------------

def ensure_dirs() -> None:
    """Р“Р°СЂР°РЅС‚РёСЂСѓРµРј РЅР°Р»РёС‡РёРµ РєР°С‚Р°Р»РѕРіР° РґР»СЏ СЃС‹СЂС‹С… Р°СЂС‚РµС„Р°РєС‚РѕРІ."""
    DATA_RAW.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    """РљРѕСЂРѕС‚РєРёР№ РїРѕРјРѕС‰РЅРёРє РґР»СЏ С‡С‚РµРЅРёСЏ РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ."""
    return os.environ.get(name, default)
# -----------------------
# Vendor hints by IP ranges
# -----------------------


# -----------------------
# Vendor hints by IP ranges
# -----------------------

def _load_vendor_hints() -> list[dict]:
    hints_file = COLLECT_CFG_DIR / "vendor_hints.json"
    try:
        if hints_file.exists():
            raw = json.loads(hints_file.read_text(encoding="utf-8"))
            items = raw.get("ranges") if isinstance(raw, dict) else raw
            if isinstance(items, list):
                return [i for i in items if isinstance(i, dict) and i.get("cidr") and i.get("vendor")]
    except Exception:
        pass
    return []

_VENDOR_HINTS = _load_vendor_hints()


def vendor_hint_for_ip(ip: str) -> str | None:
    try:
        addr = ipaddress.ip_address(ip)
    except Exception:
        return None
    for item in _VENDOR_HINTS:
        try:
            net = ipaddress.ip_network(str(item.get("cidr")), strict=False)
            if addr in net:
                return str(item.get("vendor"))
        except Exception:
            continue
    return None


def _load_external_profile(dt_base: str) -> Dict:
    """Load command profile override from config/collect.

    Supports JSON file with keys {"pre_enable": bool, "commands": [..]}
    or plain .txt with one command per line (non-empty, not starting with '#').
    """
    try:
        # prefer JSON
        js = (COLLECT_CFG_DIR / f"{dt_base}.json")
        if js.exists():
            raw = json.loads(js.read_text(encoding="utf-8"))
            prof: Dict[str, object] = {}
            if isinstance(raw, dict):
                if isinstance(raw.get("pre_enable"), bool):
                    prof["pre_enable"] = raw["pre_enable"]
                if isinstance(raw.get("commands"), list):
                    prof["commands"] = [str(x) for x in raw["commands"] if str(x).strip()]
            return prof
        # fallback to .txt
        txt = (COLLECT_CFG_DIR / f"{dt_base}.txt")
        if txt.exists():
            cmds: List[str] = []
            pre_enable = None
            for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    # allow directive like: # pre_enable=true
                    if s.lower().startswith("# pre_enable="):
                        val = s.split("=", 1)[1].strip().lower()
                        pre_enable = (val in ("1", "true", "yes", "on"))
                    continue
                cmds.append(s)
            prof2: Dict[str, object] = {}
            if pre_enable is not None:
                prof2["pre_enable"] = bool(pre_enable)
            if cmds:
                prof2["commands"] = cmds
            return prof2
    except Exception:
        pass
    return {}


def profile_for_device_type(device_type: str) -> Dict:
    """Return merged command profile for a device_type with external overrides."""
    base = device_type.replace("_telnet", "")
    prof = dict(COMMANDS_BY_TYPE.get(device_type, COMMANDS_BY_TYPE.get(base, COMMANDS_BY_TYPE["generic"])))
    override = _load_external_profile(base)
    if override.get("pre_enable") is not None:
        prof["pre_enable"] = bool(override["pre_enable"])  # type: ignore[index]
    if override.get("commands"):
        prof["commands"] = list(override["commands"])  # type: ignore[index]
    return prof


def iter_targets(seed_ips: Iterable[str], cidrs: Iterable[str]) -> Iterable[str]:
    """
    Р“РµРЅРµСЂР°С‚РѕСЂ Р°РґСЂРµСЃРѕРІ:
      - СЃРїРµСЂРІР° РІРµСЂРЅС‘С‚ СЏРІРЅРѕ Р·Р°РґР°РЅРЅС‹Рµ IP/РёРјРµРЅР° (seed_ips),
      - Р·Р°С‚РµРј СЂР°Р·РІРµСЂРЅС‘С‚ РІСЃРµ РїРѕРґСЃРµС‚Рё РёР· cidrs Рё РІРµСЂРЅС‘С‚ host-Р°РґСЂРµСЃР°.
    Р”СѓР±Р»РёРєР°С‚С‹ РѕС‚С„РёР»СЊС‚СЂРѕРІС‹РІР°СЋС‚СЃСЏ.
    """
    seen = set()
    # РџСЂСЏРјС‹Рµ С†РµР»Рё
    for t in seed_ips:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        yield t
    # РџРѕРґСЃРµС‚Рё
    for c in cidrs:
        c = c.strip()
        if not c:
            continue
        net = ipaddress.ip_network(c, strict=False)
        for ip in net.hosts():
            s = str(ip)
            if s not in seen:
                seen.add(s)
                yield s


def merge_commands_for(device_type: str) -> Dict:
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ РїСЂРѕС„РёР»СЊ РєРѕРјР°РЅРґ РґР»СЏ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ device_type,
    СЂР°Р·РІРѕСЂР°С‡РёРІР°СЏ 'extends' РµСЃР»Рё РѕРЅ Р·Р°РґР°РЅ.
    """
    prof = profile_for_device_type(device_type)
    if "extends" in prof:
        base = profile_for_device_type(prof["extends"])  # type: ignore[index]
        merged = dict(base)
        merged.update({k: v for k, v in prof.items() if k != "extends"})
        return merged
    return prof


# -----------------------
# РћРЎРќРћР’РќРђРЇ Р РђР‘РћР§РђРЇ Р›РћР“РРљРђ
# -----------------------

def gather_one(ip: str, creds: Dict[str, str]) -> Dict:
    """
    РџС‹С‚Р°РµРјСЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ Рє Р°РґСЂРµСЃСѓ ip, РїРµСЂРµР±РёСЂР°СЏ device_type Рё С‚СЂР°РЅСЃРїРѕСЂС‚ (SSHв†’Telnet).
    РџСЂРё СѓСЃРїРµС…Рµ вЂ” РІС‹РїРѕР»РЅСЏРµРј РєРѕРјР°РЅРґС‹ Рё СЃРѕС…СЂР°РЅСЏРµРј РІС‹РІРѕРґС‹ РІ data/raw/<ip>.txt.

    Р’РѕР·РІСЂР°С‰Р°РµРј РєСЂР°С‚РєРёР№ РёС‚РѕРі:
      {"ip": "...", "status": "ok", "device_type": "..."}  Р»РёР±Рѕ
      {"ip": "...", "status": "fail", "errors": ["...","..."]}
    """
    errors: List[str] = []
    # Per-host deadline to avoid long stalls
    try:
        deadline_sec = float(env("HOST_DEADLINE", "120"))
    except Exception:
        deadline_sec = 120.0
    deadline = time.time() + max(10.0, deadline_sec)

    # Determine primary device_type: prefer PREFER_VENDOR/env hints, then autodetect
    primary_dt: str | None = None
    tcp_probe_to = float(env("TCP_TIMEOUT", "1"))
    ssh_open = is_port_open(ip, 22, tcp_probe_to)
    telnet_open = is_port_open(ip, 23, tcp_probe_to)

    pref = (env("PREFER_VENDOR") or "").strip()
    if pref:
        primary_dt = pref
    else:
        # Hints priority: raw file > vendor_hints.json > autodetect
        hint = vendor_hint_from_raw(ip) or vendor_hint_for_ip(ip)
        if hint:
            primary_dt = hint
        elif SSHDetect is not None and ssh_open and env("DETECT", "1").strip() != "0":
            try:
                guesser = SSHDetect(
                    device_type="autodetect",
                    host=ip,
                    username=creds["user"],
                    password=creds["pass"],
                    timeout=float(env("AUTH_TIMEOUT", "20")),
                )
                best = guesser.autodetect()
                if best:
                    primary_dt = NETMIKO_TO_PROFILE.get(best, best)
            except Exception as e:
                errors.append(f"autodetect_ssh: {e}")

    # Compose try-order: detected first, then defaults
    order: List[str] = []
    if primary_dt:
        order = [primary_dt]
    else:
        order = list(DEVICE_TRY_ORDER)

    # РџСЂРѕС…РѕРґРёРј РїРѕ СЃРїРёСЃРєСѓ РєР°РЅРґРёРґР°С‚РѕРІ (РІРµРЅРґРѕСЂРѕРІ)
    for base_dt in order:
        # Р”РІРµ РїРѕРїС‹С‚РєРё: СЃРЅР°С‡Р°Р»Р° SSH, Р·Р°С‚РµРј Telnet
        for transport in ("ssh", "telnet"):
            if transport == "telnet" and not is_port_open(ip, 23, float(env("TCP_TIMEOUT", "1"))):
                continue
            if time.time() > deadline:
                errors.append("deadline_exceeded")
                break
            dt = base_dt if transport == "ssh" else f"{base_dt}_telnet"
            profile = merge_commands_for(dt)
            commands = profile.get("commands", ["show running-config"])
            pre_enable = profile.get("pre_enable", False)

            # Р“РѕС‚РѕРІРёРј РїР°СЂР°РјРµС‚СЂС‹ РґР»СЏ Netmiko
            params = {
                "host": ip,
                "username": creds["user"],
                "password": creds["pass"],
                "device_type": dt,
                # РЇРІРЅРѕ Р·Р°РґР°С‘Рј С‚Р°Р№РјР°СѓС‚С‹ (Р±РµСЂС‘Рј РёР· env, РєРѕС‚РѕСЂРѕРµ Р·Р°РїРѕР»РЅРёР»Рё РёР· Р°СЂРіСѓРјРµРЅС‚РѕРІ CLI)
                "conn_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "auth_timeout": int(env("AUTH_TIMEOUT", "20")),
                "banner_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "timeout": int(env("AUTH_TIMEOUT", "20")),
                "session_timeout": max(int(env("CONNECT_TIMEOUT", "12")), int(env("AUTH_TIMEOUT", "20"))) + 2,
                "fast_cli": True,
            }
            if creds.get("secret"):
                params["secret"] = creds["secret"]

            try:
                # 1) РџРѕРґРєР»СЋС‡РµРЅРёРµ
                conn = ConnectHandler(**params)

                # 2) enable СЂРµР¶РёРј (РµСЃР»Рё РЅСѓР¶РµРЅ Рё Р·Р°РґР°РЅ secret)
                if pre_enable and creds.get("secret"):
                    try:
                        conn.enable()
                    except Exception as ee:
                        # РќРµ РєСЂРёС‚РёС‡РЅРѕ вЂ” РїСЂРѕРґРѕР»Р¶Р°РµРј Р±РµР· enable
                        errors.append(f"{dt}: enable() failed: {ee}")

                # 3) Р’С‹РїРѕР»РЅРёС‚СЊ РєРѕРјР°РЅРґС‹ РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅРѕ Рё СЃРѕР±СЂР°С‚СЊ РєСѓСЃРєРё
                chunks: List[str] = []
                for cmd in commands:
                    try:
                        read_to = int(env("SENDCMD_TIMEOUT", "45"))
                        out = conn.send_command(cmd, read_timeout=read_to)
                        # РњР°СЂРєРµСЂС‹ РєРѕРјР°РЅРґ вЂ” РґР»СЏ СѓРґРѕР±РЅРѕРіРѕ РґР°Р»СЊРЅРµР№С€РµРіРѕ РїР°СЂСЃРёРЅРіР°
                        chunks.append("\n\n$ " + cmd + "\n" + (out or ""))
                    except Exception as e_cmd:
                        chunks.append("\n\n$ " + cmd + "\n" + f"[ERROR executing command: {e_cmd}]")

                # 4) РЎРѕС…СЂР°РЅРёС‚СЊ РІ С„Р°Р№Р» РїРѕ IP (hostname РІС‹С‚Р°С‰РёРј РїРѕР·Р¶Рµ РЅР° Р­С‚Р°РїРµ 2)
                ensure_dirs()
                out_path = DATA_RAW / f"{ip}.txt"
                out_path.write_text("\n".join(chunks), encoding="utf-8", errors="ignore")

                # 5) Р—Р°РєСЂС‹С‚СЊ СЃРµСЃСЃРёСЋ Рё РІРµСЂРЅСѓС‚СЊ СѓСЃРїРµС…
                try:
                    conn.disconnect()
                except Exception:
                    pass

                return {"ip": ip, "status": "ok", "device_type": dt}
            except Exception as e:
                # РљРѕРїРёРј РѕС€РёР±РєРё Рё РїСЂРѕР±СѓРµРј СЃР»РµРґСѓСЋС‰РёР№ С‚РёРї/С‚СЂР°РЅСЃРїРѕСЂС‚
                errors.append(f"{dt}: {e}")

    # Р•СЃР»Рё СЃСЋРґР° РґРѕС€Р»Рё вЂ” РІСЃРµ РїРѕРїС‹С‚РєРё РїСЂРѕРІР°Р»РёР»РёСЃСЊ
    return {"ip": ip, "status": "fail", "errors": errors[:4]}  # СЃСЂРµР·, С‡С‚РѕР±С‹ РЅРµ СЂР°Р·РґСѓРІР°С‚СЊ Р»РѕРі


def main() -> None:
    """
    РўРѕС‡РєР° РІС…РѕРґР°: С‡РёС‚Р°РµРј РїР°СЂР°РјРµС‚СЂС‹ CLI, СЃРїСЂР°С€РёРІР°РµРј РєСЂРµРґС‹ (РёР»Рё Р±РµСЂС‘Рј РёР· env),
    Р·Р°РїСѓСЃРєР°РµРј РїР°СЂР°Р»Р»РµР»СЊРЅС‹Р№ СЃР±РѕСЂ Рё РїРµС‡Р°С‚Р°РµРј СЃРІРѕРґРЅСѓСЋ С‚Р°Р±Р»РёС†Сѓ.
    """
    parser = argparse.ArgumentParser(
        description="Р­С‚Р°Рї 1: СЃР±РѕСЂ РІС‹РІРѕРґРѕРІ РєРѕРјР°РЅРґ РїРѕ SSH/Telnet Р±РµР· РёРЅРІРµРЅС‚Р°СЂРЅРѕРіРѕ С„Р°Р№Р»Р°."
    )
    parser.add_argument("--targets", nargs="*", default=[], help="РЎРїРёСЃРѕРє IP/РёРјС‘РЅ (С‡РµСЂРµР· РїСЂРѕР±РµР»)")
    parser.add_argument("--cidr", nargs="*", default=[], help="РЎРїРёСЃРѕРє РїРѕРґСЃРµС‚РµР№ РІ С„РѕСЂРјР°С‚Рµ CIDR")
    parser.add_argument("--max-workers", type=int, default=int(env("MAX_WORKERS", "20")),
                        help="РљРѕР»РёС‡РµСЃС‚РІРѕ РїР°СЂР°Р»Р»РµР»СЊРЅС‹С… РїРѕС‚РѕРєРѕРІ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РёР· env MAX_WORKERS РёР»Рё 20)")
    parser.add_argument("--conn-timeout", type=float, default=3.0,
                        help="TCP connect timeout (sec) РґР»СЏ Netmiko")
    parser.add_argument("--auth-timeout", type=float, default=5.0,
                        help="Auth/login timeout (sec) РґР»СЏ Netmiko")
    parser.add_argument("--tcp-timeout", type=float, default=1.0, help="TCP check timeout (sec) РґР»СЏ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅРѕР№ РїСЂРѕРІРµСЂРєРё РїРѕСЂС‚РѕРІ 22/23")
    
    parser.add_argument("--tcp-workers", type=int, default=int(env("TCP_WORKERS", "64")),
                        help="Parallel workers for 22/23 TCP probing")
    args = parser.parse_args()
    os.environ["CONNECT_TIMEOUT"] = str(int(args.conn_timeout))
    os.environ["AUTH_TIMEOUT"] = str(int(args.auth_timeout))

    # РљСЂРµРґС‹: Р±РµСЂС‘Рј РёР· РѕРєСЂСѓР¶РµРЅРёСЏ РёР»Рё СЃРїСЂР°С€РёРІР°РµРј
    user = env("NET_USER") or input("Username: ")
    pwd = env("NET_PASS") or getpass.getpass("Password: ")
    secret = env("NET_ENABLE", "")

    creds = {"user": user, "pass": pwd, "secret": secret}

    # РС‚РѕРіРѕРІС‹Р№ РЅР°Р±РѕСЂ С†РµР»РµР№
    targets = list(iter_targets(args.targets, args.cidr))
    # --- РСЃРєР»СЋС‡Р°РµРј РёР· СЃРєР°РЅР° IP Рё РїРѕРґСЃРµС‚Рё РёР· EXCLUDE_IPS (csv) ---
    # РџСЂРёРјРµСЂ: EXCLUDE_IPS=10.12.0.26,10.12.0.10,10.12.0.0/24,10.10.0.0/24
    _excl_raw = os.environ.get("EXCLUDE_IPS", "")
    _exclude_specs = [x.strip() for x in _excl_raw.split(",") if x.strip()]

    _exclude_networks = []
    _exclude_ips = set()
    import ipaddress

    for spec in _exclude_specs:
        try:
            if "/" in spec:
                _exclude_networks.append(ipaddress.ip_network(spec, strict=False))
            else:
                # В«Р“РѕР»С‹Р№В» СЃРµС‚РµРІРѕР№ Р°РґСЂРµСЃ в†’ СЃС‡РёС‚Р°РµРј /24 (Р° РµСЃР»Рё x.y.0.0 вЂ” /16)
                parts = spec.split(".")
                if len(parts) == 4 and parts[2] == "0" and parts[3] == "0":
                    _exclude_networks.append(ipaddress.ip_network(f"{parts[0]}.{parts[1]}.0.0/16", strict=False))
                elif len(parts) == 4 and parts[3] == "0":
                    _exclude_networks.append(ipaddress.ip_network(f"{parts[0]}.{parts[1]}.{parts[2]}.0/24", strict=False))
                else:
                    _exclude_ips.add(str(ipaddress.ip_address(spec)))
        except Exception as e:
            console.print(f"[yellow]Warning: bad EXCLUDE_IPS entry '{spec}': {e}[/]")

    if _exclude_networks or _exclude_ips:
        before = len(targets)
        filtered: List[str] = []
        for t in targets:
            try:
                ip = ipaddress.ip_address(t)
            except Exception:
                # РµСЃР»Рё РІРґСЂСѓРі t РЅРµ IP вЂ” РїСЂРѕРїСѓСЃРєР°РµРј (РЅРµ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ)
                continue

            if str(ip) in _exclude_ips:
                continue

            skip = False
            for net in _exclude_networks:
                if ip in net:
                    skip = True
                    break
            if skip:
                continue

            filtered.append(str(ip))

        targets = filtered
        console.print(f"[yellow]Excluded {_exclude_specs} вЂ” {before - len(targets)} host(s) removed from scan[/]")
    # --- РєРѕРЅРµС† Р±Р»РѕРєР° РёСЃРєР»СЋС‡РµРЅРёР№ ---
# РµСЃР»Рё СЃРїРёСЃРѕРє РїСѓСЃС‚ вЂ” РЅРёС‡РµРіРѕ РЅРµ РїРµС‡Р°С‚Р°РµРј Рё РЅРµ С‚СЂРѕРіР°РµРј targets
    if not targets:
        console.print("[red]РќРµ Р·Р°РґР°РЅРѕ РЅРё РѕРґРЅРѕР№ С†РµР»Рё (--targets/--cidr). Р—Р°РІРµСЂС€РµРЅРёРµ.[/]")
        return

    console.print(f"[bold]Р’СЃРµРіРѕ РїРѕС‚РµРЅС†РёР°Р»СЊРЅС‹С… С†РµР»РµР№:[/] {len(targets)}")
    # Р‘С‹СЃС‚СЂС‹Р№ РѕС‚Р±РѕСЂ РїРѕ РѕС‚РєСЂС‹С‚С‹Рј РїРѕСЂС‚Р°Рј 22/23 вЂ” С‡С‚РѕР±С‹ РЅРµ Р·Р°Р»РёРїР°С‚СЊ РЅР° С‚Р°Р№Рј-Р°СѓС‚Р°С… Netmiko
    # РџР°СЂР°Р»Р»РµР»СЊРЅС‹Р№ РѕС‚Р±РѕСЂ РїРѕ РѕС‚РєСЂС‹С‚С‹Рј РїРѕСЂС‚Р°Рј 22/23 вЂ” РіРѕСЂР°Р·РґРѕ Р±С‹СЃС‚СЂРµРµ РЅР° Р±РѕР»СЊС€РёС… СЃРїРёСЃРєР°С…
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    def _check_host(h: str) -> str | None:
        try:
            if is_port_open(h, 22, args.tcp_timeout) or is_port_open(h, 23, args.tcp_timeout):
                return h
        except Exception:
            return None
        return None

    live: List[str] = []
    # РћРіСЂР°РЅРёС‡РёРІР°РµРј РїР°СЂР°Р»Р»РµР»СЊРЅРѕСЃС‚СЊ РґР»СЏ РїСЂРѕРІРµСЂРєРё РїРѕСЂС‚РѕРІ (РЅРµ РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ СЂР°РІРЅР° args.max_workers)
    # Use dedicated TCP worker pool size to accelerate port probing on large target sets
    try:
        tcp_workers_opt = int(os.environ.get("TCP_WORKERS", "0"))
    except Exception:
        tcp_workers_opt = 0
    # Prefer CLI arg if present (added below if available), else env, else derive from max_workers
    if hasattr(args, "tcp_workers") and args.tcp_workers:
        tcp_workers = int(args.tcp_workers)
    elif tcp_workers_opt > 0:
        tcp_workers = tcp_workers_opt
    else:
        tcp_workers = args.max_workers
    tcp_workers = min(256, max(4, int(tcp_workers)))
    with ThreadPoolExecutor(max_workers=tcp_workers) as _ex:
        futs = { _ex.submit(_check_host, h): h for h in targets }
        for fut in _as_completed(futs):
            try:
                res = fut.result()
                if res:
                    live.append(res)
            except Exception:
                # РёРіРЅРѕСЂРёСЂСѓРµРј РµРґРёРЅРёС‡РЅС‹Рµ РѕС€РёР±РєРё РїСЂРѕРІРµСЂРєРё
                continue

    console.print(f"[bold]РҐРѕСЃС‚РѕРІ СЃ РѕС‚РєСЂС‹С‚С‹Рј 22/23:[/] {len(live)}")
    if not live:
        console.print("[yellow]РќРµС‚ С…РѕСЃС‚РѕРІ СЃ РѕС‚РєСЂС‹С‚С‹Рј 22/23. Р—Р°РІРµСЂС€РµРЅРёРµ СЃРєР°РЅР°.[/]")
        return
    ensure_dirs()
    total = len(live)

    # РџСЂРѕРіСЂРµСЃСЃ-Р±Р°СЂ
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=True,
    )
    task_id = progress.add_task("РЎР±РѕСЂ CLI", total=total)

    results: List[Dict] = []
    with progress:
        with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            futs = {ex.submit(gather_one, ip, creds): ip for ip in live}
            done = 0
            pending = set(futs.keys())
            import time as _time
            last_hb = _time.time()
            while pending:
                try:
                    completed_any = False
                    for fut in as_completed([_f for _f in pending], timeout=5):
                        res = fut.result()
                        results.append(res)
                        done += 1
                        pending.remove(fut)
                        progress.update(task_id, completed=done)
                        ip = res.get("ip") or res.get("host") or "?"
                        st = res.get("status", "unknown")
                        info = res.get("device_type") or res.get("info") or ""
                        console.print(f"[dim]{done}/{total}[/] {ip}: {st} {info}")
                        completed_any = True
                    if not completed_any:
                        raise TimeoutError
                except TimeoutError:
                    now = _time.time()
                    if now - last_hb >= 5:
                        console.print(f"[cyan]heartbeat[/] done {done}/{total}")
                        last_hb = now

    # РЎРІРѕРґРЅР°СЏ С‚Р°Р±Р»РёС†Р° РїРѕ РёС‚РѕРіР°Рј
    table = Table(title="Stage 1: Collection results")
    table.add_column("IP/Host")
    table.add_column("Status")
    table.add_column("Info / Errors")

    ok_count = 0
    for r in results:
        if r["status"] == "ok":
            ok_count += 1
            table.add_row(r["ip"], "[green]ok[/]", r.get("device_type", ""))
        else:
            info = "; ".join(r.get("errors", []))
            if len(info) > 120:
                info = info[:117] + "..."
            table.add_row(r["ip"], "[red]fail[/]", info)

    console.print(table)
    console.print(f"[bold]РЈСЃРїРµС€РЅРѕ СЃРѕР±СЂР°РЅС‹ СѓСЃС‚СЂРѕР№СЃС‚РІР°:[/] {ok_count} / {len(results)}")
    console.print(f"[bold]РђСЂС‚РµС„Р°РєС‚С‹:[/] {DATA_RAW.resolve()}")

if __name__ == "__main__":
    main()






def _guess_vendor_from_text(s: str) -> str | None:
    t = (s or "").lower()
    if "routeros" in t or "mikrotik" in t:
        return "mikrotik"
    if "eltex" in t or " mes" in t:
        return "eltex_mes"
    if "huawei" in t or " vrp" in t:
        return "huawei_vrp"
    if "d-link" in t or " dgs" in t or " des-" in t:
        return "dlink"
    if "qtech" in t or " qsw" in t:
        return "qtech"
    if "cisco ios" in t or "ios-xe" in t or "cisco" in t:
        return "cisco_ios"
    return None


def vendor_hint_from_raw(ip: str) -> str | None:
    """Peek into data/raw/<ip>.txt to guess previous vendor quickly."""
    p = DATA_RAW / f"{ip}.txt"
    try:
        if p.exists():
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
            return _guess_vendor_from_text(head)
    except Exception:
        return None
    return None

