#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 1: fast CLI collection from network devices.

Features:
- Parallel TCP probe for 22/23 ports
- Vendor hint by raw files (data/raw/<ip>.txt) and optional config/collect/vendor_hints.json
- Optional SSH autodetect (Netmiko) when DETECT!=0
- Per-host deadline + reduced timeouts to avoid stalls
- Heartbeat logs while waiting for futures
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from netmiko import ConnectHandler
try:
    from netmiko.ssh_autodetect import SSHDetect  # type: ignore
except Exception:  # pragma: no cover
    SSHDetect = None


# Paths
DATA_RAW = Path("data") / "raw"
COLLECT_CFG_DIR = Path("config") / "collect"
TEXTFSM_DIR = Path("templates") / "textfsm"

# Command profiles
COMMANDS_BY_TYPE: Dict[str, Dict] = {
    "cisco_ios": {
        "pre_enable": True,
        "commands": [
            "terminal length 0",
            "show version",
            "show lldp neighbors detail",
        ],
    },
    "cisco_ios_telnet": {"extends": "cisco_ios"},
    "hp_procurve": {
        "pre_enable": False,
        "commands": [
            "show version",
            "show lldp info remote-device detail",
        ],
    },
    "hp_procurve_telnet": {"extends": "hp_procurve"},
    "juniper_junos": {
        "pre_enable": False,
        "commands": [
            "show version",
            "show lldp neighbors detail",
        ],
    },
    "juniper_junos_telnet": {"extends": "juniper_junos"},
    "dlink": {
        "pre_enable": False,
        "commands": [
            "show version",
            "show lldp remote_ports",
            "show vlan",
            "show interfaces status",
        ],
    },
    "dlink_telnet": {"extends": "dlink"},
    "nis": {
        "pre_enable": False,
        "commands": [
            "show running-config",
            "show interface * status",
            "show lldp neighbors",
        ],
    },
    "nis_telnet": {"extends": "nis"},
    "snr": {
        "pre_enable": False,
        "commands": [
            "show version",
            "show lldp neighbors brief",
            "show running-config",
        ],
    },
    "generic": {
        "pre_enable": False,
        "commands": ["show version"],
    },
    "generic_telnet": {"extends": "generic"},
}

NETMIKO_TO_PROFILE = {
    "cisco_ios": "cisco_ios",
    "hp_procurve": "hp_procurve",
    "aruba_procurve": "hp_procurve",
    "juniper_junos": "juniper_junos",
    "juniper": "juniper_junos",
    "eltex": "eltex_mes",
    "dlink_ds": "dlink",
    "mikrotik_routeros": "mikrotik",
    "huawei": "huawei_vrp",
}

DEVICE_TRY_ORDER = [
    "cisco_ios",
    "snr",
    "osnova",
    "eltex_mes",
    "dlink",
    "nis",
    "hp_procurve",
    "juniper_junos",
    "generic",
]

# Map profile/vendor id -> Netmiko device_type base
PROFILE_TO_NETMIKO = {
    "cisco_ios": "cisco_ios",
    "eltex_mes": "eltex",
    "dlink": "dlink_ds",
    "hp_procurve": "hp_procurve",
    "juniper_junos": "juniper_junos",
    "mikrotik": "mikrotik_routeros",
    "huawei_vrp": "huawei",
    "qtech": "cisco_ios",
    "generic": "cisco_ios",
    "nis": "cisco_ios",
    "zes": "cisco_ios",
    "osnova": "cisco_ios",
    "snr": "cisco_ios",
}

console = Console()


def ensure_dirs() -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# Vendor hints (config + raw files)
def _load_vendor_hints() -> List[Dict[str, str]]:
    p = COLLECT_CFG_DIR / "vendor_hints.json"
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            items = raw.get("ranges") if isinstance(raw, dict) else raw
            return [i for i in items or [] if isinstance(i, dict) and i.get("cidr") and i.get("vendor")]
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
            if addr in ipaddress.ip_network(str(item.get("cidr")), strict=False):
                return str(item.get("vendor"))
        except Exception:
            continue
    return None


def _guess_vendor_from_text(s: str) -> str | None:
    t = (s or "").lower()
    if "routeros" in t or "mikrotik" in t:
        return "mikrotik"
    if "eltex" in t or " mes" in t:
        return "eltex_mes"
    if "huawei" in t or " vrp" in t:
        return "huawei_vrp"
    if "d-link" in t or " dgs" in t or " des-" in t or "des-" in t or "dgs-" in t:
        return "dlink"
    if "qtech" in t or " qsw" in t:
        return "qtech"
    if "cisco ios" in t or "ios-xe" in t or "cisco" in t:
        return "cisco_ios"
    return None


def vendor_hint_from_raw(ip: str) -> str | None:
    p = DATA_RAW / f"{ip}.txt"
    try:
        if p.exists():
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
            return _guess_vendor_from_text(head)
    except Exception:
        return None
    return None


PROFILE_DIR_ALIASES = {
    # Map Netmiko device types or internal names to a templates/textfsm vendor dir
    "cisco_xe": "cisco_ios",
    "mikrotik_routeros": "mikrotik",
    "huawei": "huawei_vrp",
    "dlink_ds": "dlink",
    "eltex": "eltex_mes",
}


def _load_external_profile(dt_base: str) -> Dict:
    try:
        js = COLLECT_CFG_DIR / f"{dt_base}.json"
        if js.exists():
            raw = json.loads(js.read_text(encoding="utf-8"))
            prof: Dict[str, object] = {}
            if isinstance(raw, dict):
                if isinstance(raw.get("pre_enable"), bool):
                    prof["pre_enable"] = raw["pre_enable"]
                if isinstance(raw.get("commands"), list):
                    prof["commands"] = [str(x) for x in raw["commands"] if str(x).strip()]
            return prof
        txt = COLLECT_CFG_DIR / f"{dt_base}.txt"
        if txt.exists():
            cmds: List[str] = []
            pre_enable = None
            for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    ls = s.lower()
                    if ls.startswith("# pre_enable="):
                        val = ls.split("=", 1)[1].strip()
                        pre_enable = (val in ("1", "true", "yes", "on"))
                    continue
                cmds.append(s)
            prof2: Dict[str, object] = {}
            if pre_enable is not None:
                prof2["pre_enable"] = bool(pre_enable)
            if cmds:
                prof2["commands"] = cmds
            return prof2

        # Fallback: commands from templates/textfsm/<vendor>/example.txt
        vendor_dir = TEXTFSM_DIR / PROFILE_DIR_ALIASES.get(dt_base, dt_base)
        ex_txt = vendor_dir / "example.txt"
        if ex_txt.exists():
            cmds2: List[str] = []
            pre_enable2 = None
            try:
                for line in ex_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith("#"):
                        ls = s.lower()
                        if ls.startswith("# pre_enable="):
                            val = ls.split("=", 1)[1].strip()
                            pre_enable2 = (val in ("1", "true", "yes", "on"))
                        continue
                    cmds2.append(s)
            except Exception:
                cmds2 = []
            prof3: Dict[str, object] = {}
            if pre_enable2 is not None:
                prof3["pre_enable"] = bool(pre_enable2)
            if cmds2:
                prof3["commands"] = cmds2
            if prof3:
                return prof3
    except Exception:
        pass
    return {}


def profile_for_device_type(device_type: str) -> Dict:
    base = device_type.replace("_telnet", "")
    prof = dict(COMMANDS_BY_TYPE.get(device_type, COMMANDS_BY_TYPE.get(base, COMMANDS_BY_TYPE["generic"])))
    override = _load_external_profile(base)
    if override.get("pre_enable") is not None:
        prof["pre_enable"] = bool(override["pre_enable"])  # type: ignore[index]
    if override.get("commands"):
        prof["commands"] = list(override["commands"])  # type: ignore[index]
    return prof


def iter_targets(seed_ips: Iterable[str], cidrs: Iterable[str]) -> Iterable[str]:
    seen = set()
    for t in seed_ips:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        yield t
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
    prof = profile_for_device_type(device_type)
    if "extends" in prof:
        base = profile_for_device_type(prof["extends"])  # type: ignore[index]
        merged = dict(base)
        merged.update({k: v for k, v in prof.items() if k != "extends"})
        return merged
    return prof


def is_port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def gather_one(ip: str, creds: Dict[str, str]) -> Dict:
    errors: List[str] = []
    # per-host deadline
    try:
        deadline_sec = float(env("HOST_DEADLINE", "90"))
    except Exception:
        deadline_sec = 90.0
    deadline = time.time() + max(10.0, deadline_sec)

    tcp_probe_to = float(env("TCP_TIMEOUT", "1"))
    ssh_open = is_port_open(ip, 22, tcp_probe_to)
    telnet_open = is_port_open(ip, 23, tcp_probe_to)

    primary_dt: str | None = None
    pref = (env("PREFER_VENDOR") or "").strip()
    if pref:
        primary_dt = pref
    else:
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

    order: List[str] = [primary_dt] if primary_dt else list(DEVICE_TRY_ORDER)

    for base_dt in order:
        for transport in ("ssh", "telnet"):
            if transport == "telnet" and not telnet_open and (base_dt not in ("nis",)):
                continue
            if time.time() > deadline:
                errors.append("deadline_exceeded")
                break
            # Determine profile id and corresponding Netmiko type
            profile_id = base_dt
            netmiko_base = PROFILE_TO_NETMIKO.get(profile_id, profile_id)
            netmiko_type = netmiko_base if transport == "ssh" else f"{netmiko_base}_telnet"
            dt = profile_id if transport == "ssh" else f"{profile_id}_telnet"
            profile = merge_commands_for(dt)
            commands = profile.get("commands", ["show version"]) or ["show version"]
            pre_enable = bool(profile.get("pre_enable", False))

            params = {
                "host": ip,
                "username": creds["user"],
                "password": creds["pass"],
                "device_type": netmiko_type,
                "conn_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "auth_timeout": int(env("AUTH_TIMEOUT", "20")),
                "banner_timeout": int(env("CONNECT_TIMEOUT", "12")),
                "timeout": int(env("AUTH_TIMEOUT", "20")),
                "session_timeout": max(int(env("CONNECT_TIMEOUT", "12")), int(env("AUTH_TIMEOUT", "20"))) + 2,
                "fast_cli": (netmiko_type.startswith("cisco_ios")),
            }
            if creds.get("secret"):
                params["secret"] = creds["secret"]

            try:
                conn = ConnectHandler(**params)
                if pre_enable and creds.get("secret"):
                    try:
                        conn.enable()
                    except Exception as ee:
                        errors.append(f"{dt}: enable() failed: {ee}")
                chunks: List[str] = []
                for cmd in commands:
                    try:
                        read_to = int(env("SENDCMD_TIMEOUT", "45"))
                        out = conn.send_command(cmd, read_timeout=read_to)
                        chunks.append("\n\n$ " + cmd + "\n" + (out or ""))
                    except Exception as e_cmd:
                        # Fallback for prompts with escape sequences or slow prompts
                        emsg = str(e_cmd)
                        try:
                            out = conn.send_command_timing(cmd)
                            chunks.append("\n\n$ " + cmd + "\n" + (out or ""))
                        except Exception as e2:
                            chunks.append("\n\n$ " + cmd + "\n" + f"[ERROR executing command: {emsg}; fallback_timing_failed: {e2}]")
                # Decide raw output path based on hostname pattern SITE-ZONE
                full_text = "\n".join(chunks)
                try:
                    prompt = ""
                    try:
                        prompt = (conn.find_prompt() or "").strip()
                    except Exception:
                        pass
                    hn = None
                    import re as _re
                    m1 = _re.search(r"(?m)^\s*hostname\s+([\w\-.]+)", full_text)
                    if m1:
                        hn = m1.group(1)
                    if not hn:
                        m2 = _re.search(r"(?m)^\s*([\w\-.]+)\s+uptime is\s+", full_text)
                        if m2:
                            hn = m2.group(1)
                    if not hn and prompt:
                        hn = prompt.rstrip("#>")
                    site = None
                    zone = None
                    if hn and "-" in hn:
                        parts = hn.split("-")
                        if parts and parts[0].isalpha() and len(parts[0]) >= 3:
                            site = parts[0].upper()
                        # find first numeric token like 02, 105
                        for tok in parts[1:]:
                            if tok.isdigit() and 1 <= len(tok) <= 4:
                                zone = tok
                                break
                    # Build path
                    target = DATA_RAW
                    if site:
                        target = target / site
                        if zone:
                            target = target / zone
                    else:
                        target = target / "unknown"
                    target.mkdir(parents=True, exist_ok=True)
                    (target / f"{ip}.txt").write_text(full_text, encoding="utf-8", errors="ignore")
                except Exception:
                    ensure_dirs()
                    (DATA_RAW / f"{ip}.txt").write_text(full_text, encoding="utf-8", errors="ignore")
                try:
                    conn.disconnect()
                except Exception:
                    pass
                return {"ip": ip, "status": "ok", "device_type": dt}
            except Exception as e:
                errors.append(f"{dt}: {e}")

    return {"ip": ip, "status": "fail", "errors": errors[:4]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: collect CLI via SSH/Telnet with Netmiko")
    parser.add_argument("--targets", nargs="*", default=[], help="Explicit IP/host targets")
    parser.add_argument("--cidr", nargs="*", default=[], help="CIDR subnets to scan")
    parser.add_argument("--max-workers", type=int, default=int(env("MAX_WORKERS", "20")),
                        help="Parallel SSH/Telnet sessions (default from env MAX_WORKERS or 20)")
    parser.add_argument("--conn-timeout", type=float, default=3.0, help="Netmiko connect timeout")
    parser.add_argument("--auth-timeout", type=float, default=5.0, help="Netmiko auth/login timeout")
    parser.add_argument("--tcp-timeout", type=float, default=1.0, help="TCP probe timeout for 22/23")
    parser.add_argument("--tcp-workers", type=int, default=int(env("TCP_WORKERS", "64")),
                        help="Parallel workers for 22/23 probing")

    args = parser.parse_args()
    os.environ["CONNECT_TIMEOUT"] = str(int(args.conn_timeout))
    os.environ["AUTH_TIMEOUT"] = str(int(args.auth_timeout))

    user = env("NET_USER") or input("Username: ")
    pwd = env("NET_PASS") or getpass.getpass("Password: ")
    secret = env("NET_ENABLE", "")
    creds = {"user": user, "pass": pwd, "secret": secret}

    targets = list(iter_targets(args.targets, args.cidr))
    _excl_raw = os.environ.get("EXCLUDE_IPS", "")
    _exclude_specs = [x.strip() for x in _excl_raw.split(",") if x.strip()]
    _exclude_networks = []
    _exclude_ips = set()
    for spec in _exclude_specs:
        try:
            if "/" in spec:
                _exclude_networks.append(ipaddress.ip_network(spec, strict=False))
            else:
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
                continue
            if str(ip) in _exclude_ips:
                continue
            if any(ip in n for n in _exclude_networks):
                continue
            filtered.append(str(ip))
        targets = filtered
        console.print(f"[yellow]Excluded {_exclude_specs} -> {before - len(targets)} host(s) removed from scan[/]")

    if not targets:
        console.print("[red]Нет целей (--targets/--cidr).[/]")
        return

    console.print(f"[bold]Всего потенциальных целей:[/] {len(targets)}")

    # TCP probe 22/23
    live: List[str] = []
    tcp_workers = min(256, max(4, int(args.tcp_workers)))
    def _check_host(h: str) -> str | None:
        try:
            if is_port_open(h, 22, args.tcp_timeout) or is_port_open(h, 23, args.tcp_timeout):
                return h
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=tcp_workers) as _ex:
        futs = {_ex.submit(_check_host, h): h for h in targets}
        for f in as_completed(futs):
            try:
                r = f.result()
                if r:
                    live.append(r)
            except Exception:
                continue

    console.print(f"[bold]Хостов с открытым 22/23:[/] {len(live)}")
    if not live:
        console.print("[yellow]Порт 22/23 не открыт. Завершаю.[/]")
        return

    ensure_dirs()
    total = len(live)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=True,
    )
    task_id = progress.add_task("Сбор CLI", total=total)

    results: List[Dict] = []
    # Heartbeat tuning via env
    try:
        hb_interval = float(env("HEARTBEAT_INTERVAL", "30"))
    except Exception:
        hb_interval = 30.0
    hb_enabled = (env("HEARTBEAT", "1").strip() != "0")

    with progress:
        with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            futs = {ex.submit(gather_one, ip, creds): ip for ip in live}
            done = 0
            pending = set(futs.keys())
            last_hb = time.time()
            while pending:
                try:
                    completed_any = False
                    for fut in as_completed(list(pending), timeout=5):
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
                    if hb_enabled:
                        now = time.time()
                        if now - last_hb >= hb_interval:
                            console.print(f"[cyan]heartbeat[/] done {done}/{total}")
                            last_hb = now

    table = Table(title="Stage 1: Collection results")
    table.add_column("IP/Host")
    table.add_column("Status")
    table.add_column("Info / Errors")

    ok = 0
    for r in results:
        if r.get("status") == "ok":
            ok += 1
            table.add_row(r.get("ip", "?"), "[green]ok[/]", r.get("device_type", ""))
        else:
            info = "; ".join(r.get("errors", []))
            if len(info) > 120:
                info = info[:117] + "..."
            table.add_row(r.get("ip", "?"), "[red]fail[/]", info)

    console.print(table)
    console.print(f"[bold]Успешных подключений:[/] {ok} / {len(results)}")
    console.print(f"[bold]Raw out:[/] {DATA_RAW.resolve()}")


if __name__ == "__main__":
    main()
