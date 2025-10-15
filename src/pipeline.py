#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end pipeline that replaces batch logic from scripts/make_example_v2.bat.

Steps:
  1) Load .env (optional) to populate NET_USER/NET_PASS/NET_ENABLE, timeouts, workers
  2) Stage1: collect CLI via stage1_collect (optional, controlled by --steps)
  3) TextFSM parse (src.parsers.textfsm_loader)
  4) Split parsed_textfsm.json into data/input/cli/*.json (for inventory merge)
  5) Merge inventory.json with cli/*.json into inventory.merged.json
  6) Safety: if merged empty, build inventory from data/raw/*.txt
  7) Normalize (src.parsers.normalize) -> normalized.json
  8) Render (src.renderers.mermaid_writer) -> network.mmd

Usage examples:
  python -m src.pipeline --config config/config.json --env .env --cidr 10.20.98.0/30
  python -m src.pipeline --config config/config.json --steps parse,split,merge,normalize,render

Notes:
  - This module focuses on orchestration; it assumes required packages are installed.
  - On Windows, ensure the console/codepage supports UTF-8 if viewing logs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Core components
from src.parsers.textfsm_loader import Config as LoaderConfig, Inventory as LoaderInventory, TextFSMParser
from src.parsers.normalize import Inventory as NormInventory, Normalizer
from src.renderers.mermaid_writer import Config as RenderConfig, MermaidWriter, load_normalized


# -----------------------------
# Logging
# -----------------------------

def setup_logger(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("pipeline")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        fmt = logging.Formatter("[%(levelname)s] %(message)s")
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        # Optional file handler
        if log_file is not None:
            try:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(str(log_file), encoding="utf-8")
                fh.setFormatter(fmt)
                logger.addHandler(fh)
            except Exception:
                # Fallback to console-only if file handler fails
                pass
    return logger


# -----------------------------
# Utils
# -----------------------------

def project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env_file(path: Path, log: logging.Logger) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path or not path.exists():
        return env
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            env[k] = v
    except Exception as e:
        log.warning("Failed to read .env %s: %s", path, e)
    return env


def ensure_dirs(paths: Iterable[Path]) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, data: Dict, log: logging.Logger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote %s", path)


def progress_bar(done: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return "[{}] 100% ({}->{})".format("#" * width, done, total)
    filled = int(width * done / total)
    bar = "#" * filled + "." * (width - filled)
    percent = int(100 * done / total)
    return f"[{bar}] {percent}% ({done}/{total})"


# -----------------------------
# Steps
# -----------------------------

def step_collect(args, cfg: LoaderConfig, logs_dir: Path, log: logging.Logger) -> None:
    """Call stage1_collect.py as a subprocess with provided args/env.

    Kept as a subprocess call to reuse interactive credentials flow and rich UI.
    """
    cmd = [
        sys.executable,
        str(project_root_from_here() / "stage1_collect.py"),
        "--max-workers",
        str(args.max_workers),
        "--tcp-timeout",
        str(args.tcp_timeout),
        "--tcp-workers",
        str(args.tcp_workers),
        "--conn-timeout",
        str(args.conn_timeout),
        "--auth-timeout",
        str(args.auth_timeout),
    ]
    # targets/cidr
    if args.targets:
        cmd += ["--targets", *args.targets]
    if args.cidr:
        cmd += ["--cidr", *args.cidr]

    log.info("[STEP 1] Collect CLI (stage1_collect.py)")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Tee child process output to console and optional log file
    log_file_path = getattr(args, "log_file", None)
    fh = None
    try:
        if log_file_path:
            lf = Path(log_file_path)
            lf.parent.mkdir(parents=True, exist_ok=True)
            fh = lf.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root_from_here()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            print(line)
            if fh:
                fh.write(line + "\n")
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"stage1_collect exited with code {rc}")
    finally:
        if fh:
            fh.flush()
            fh.close()


def step_textfsm_parse(cfg_path: Path, inv_path: Path, parsed_out: Path, log: logging.Logger) -> None:
    log.info("[STEP 2] PARSE CLI (TextFSM -> parsed_textfsm.json)")
    cfg = LoaderConfig.load(cfg_path)
    inv = LoaderInventory.load(inv_path)
    parser = TextFSMParser(cfg, inv, log)
    parse = getattr(parser, "parse_all_fast", None) or parser.parse_all
    data = parse()
    dump_json(parsed_out, data, log)


def step_split_cli(parsed_path: Path, out_dir: Path, log: logging.Logger) -> int:
    log.info("[STEP 2.1] SPLIT parsed_textfsm.json -> %s", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(parsed_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Cannot read %s: %s", parsed_path, e)
        return 0
    hosts = data.get("hosts", {}) or {}
    def safe(name: str) -> str:
        return re.sub(r"[^0-9A-Za-z_.-]+", "_", str(name)) or "host"
    count = 0
    for key, value in hosts.items():
        fn = out_dir / f"{safe(key)}.json"
        fn.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        count += 1
    log.info("[SPLIT] wrote %d files to %s", count, out_dir)
    return count


def step_merge_inventory(base_inv: Path, cli_dir: Path, out_inv: Path, log: logging.Logger) -> Tuple[int, int]:
    log.info("[STEP 3] MERGE INVENTORY (base + cli/*.json -> %s)", out_inv)
    devs: List[Dict] = []
    try:
        if base_inv.exists():
            raw = json.loads(base_inv.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("devices"), list):
                devs.extend(raw.get("devices", []))
    except Exception as e:
        log.warning("Failed to read base inventory %s: %s", base_inv, e)

    # Helper: create/merge device
    def add_or_update(dev: Dict[str, Any]) -> None:
        host = (dev.get("hostname") or "").strip()
        ip = (str(dev.get("mgmt_ip")) or "").strip()
        if not host and not ip:
            return
        # Try to find existing by hostname OR by mgmt_ip to avoid duplicates
        for existing in devs:
            e_host = (existing.get("hostname") or "").strip()
            e_ip = (str(existing.get("mgmt_ip")) or "").strip()
            if (host and e_host and e_host == host) or (ip and e_ip and e_ip == ip):
                # Prefer human hostname over IP-like
                if e_host and e_host.replace(".", "").isdigit() and host and not host.replace(".", "").isdigit():
                    existing["hostname"] = host
                # Merge shallow fields without overwriting non-empty values
                for k, v in dev.items():
                    if k in ("interfaces", "vlans"):
                        if v:
                            existing[k] = v
                    else:
                        if v and not existing.get(k):
                            existing[k] = v
                return
        # No match — append
        devs.append(dev)

    rx = re.compile(r'(?:^|[^0-9])(\d{1,3}(?:\.\d{1,3}){3})(?:[^0-9]|$)')
    added = 0

    def _short(name: str) -> str:
        return name.split(".")[0] if name else name

    project_root = Path(__file__).resolve().parents[1]
    raw_dir = project_root / "data" / "raw"

    for fp in sorted(cli_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        m = rx.search(fp.name)
        ip = m.group(1) if m else ""
        host = (data.get("hostname") or data.get("host") or ip or "").strip()
        mgmt = str(data.get("mgmt_ip") or data.get("ip") or ip or "").strip()
        vendor = (data.get("vendor") or "").strip() or None
        parsed = data.get("parsed", {}) or {}

        device: Dict[str, Any] = {"hostname": host or mgmt, "mgmt_ip": mgmt}
        if vendor:
            device["vendor"] = vendor

        # Try to read real hostname from raw file if present
        try:
            raw_files = data.get("raw_files", []) or []
            if raw_files:
                rf = raw_dir / str(raw_files[0])
                if rf.exists():
                    txt = rf.read_text(encoding="utf-8", errors="ignore")
                    mhn = re.search(r'(?m)^\s*hostname\s+([\w\-.]+)', txt)
                    if not mhn:
                        # Cisco-like banner: '<hostname> uptime is ...'
                        mhn = re.search(r'(?m)^\s*([\w\-.]+)\s+uptime is\s+', txt)
                    if mhn:
                        device["hostname"] = mhn.group(1)
                        # Infer site as prefix before first dash (e.g., DEN-...)
                        if not device.get("site"):
                            ms = re.match(r'^([A-Za-z]{3})-', device["hostname"])  # type: ignore[index]
                            if ms:
                                device["site"] = ms.group(1).upper()
                    # Extract model hints from raw for certain vendors
                    if (device.get("vendor") or "").lower() == "dlink" or re.search(r'(?m)^#\s*(DES|DGS)-', txt):
                        mm = re.search(r'(?m)^#\s*((?:DES|DGS)-[0-9A-Za-z\-]+)\b', txt)
                        if mm and not device.get("model"):
                            device["model"] = mm.group(1)
                    if (device.get("vendor") or "").lower() == "eltex_mes" and not device.get("model"):
                        msd = re.search(r'(?m)^\s*System Description\s*:\s*(.+)', txt)
                        if msd:
                            sdesc = msd.group(1).strip()
                            mm = re.search(r'\b(MES\S+)', sdesc)
                            device["model"] = (mm.group(1) if mm else sdesc)
        except Exception:
            pass

        # Site mapping by IP (CIDR rules)
        try:
            site_map = [
                ("MSK", ipaddress.ip_network("10.0.2.0/24")),
                ("NSK", ipaddress.ip_network("10.2.99.0/24")),
            ]
            if mgmt:
                ip = ipaddress.ip_address(mgmt)
                for name, net in site_map:
                    if ip in net:
                        device["site"] = name
                        break
        except Exception:
            pass

        # Model/version per vendor
        if parsed.get("cisco_ios_show_version"):
            v0 = parsed["cisco_ios_show_version"][0]
            device["model"] = v0.get("Model") or device.get("model")
        if parsed.get("osnova_show_version"):
            v0 = parsed["osnova_show_version"][0]
            device["model"] = device.get("model") or (v0.get("Firmware") or "OSNOVA")
        if parsed.get("eltex_mes_show_system_information"):
            v0 = parsed["eltex_mes_show_system_information"][0]
            # Derive model from SystemDescription (e.g., 'MES2424P rev.C1 ...')
            sdesc = (v0.get("SystemDescription") or "").strip()
            mm = re.search(r'\b(MES\S+)', sdesc)
            if mm:
                device["model"] = device.get("model") or mm.group(1)
            else:
                device["model"] = device.get("model") or sdesc or None
        if parsed.get("dlink_show_config_header"):
            v0 = parsed["dlink_show_config_header"][0]
            mdl = (v0.get("Model") or "").strip()
            if mdl:
                device["model"] = device.get("model") or mdl

        # VLANs per vendor
        vlan_map: Dict[int, Dict[str, Any]] = {}
        for key in ("cisco_ios_show_vlan_brief", "eltex_mes_show_vlan", "dlink_show_vlan"):
            for row in parsed.get(key, []) or []:
                vid = str(row.get("VlanId") or "").strip()
                name = str(row.get("VlanName") or "").strip() or None
                if vid.isdigit():
                    try:
                        vi = int(vid)
                    except Exception:
                        continue
                    if 1 <= vi <= 4094:  # filter noise
                        # Filter out obvious counter words accidentally matched
                        bad = {"packets", "input", "output", "unknown", "minute", "runts", "runts,",
                               "watchdog", "watchdog,", "babbles", "babbles,", "lost", "errors", "symbol",
                               "oversize", "pause", "broadcasts", "excessive"}
                        nm = (name or "").strip()
                        if nm.lower() in bad:
                            nm = None
                        vlan_map[vi] = {"id": vi, "name": nm or None}
        if vlan_map:
            device["vlans"] = sorted(vlan_map.values(), key=lambda x: x["id"])  # dedup + order

        # Interfaces / links from CDP/LLDP
        if parsed.get("cisco_ios_show_cdp_neighbors_detail"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["cisco_ios_show_cdp_neighbors_detail"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("Neighbor") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs
        # Cisco CDP neighbors (brief)
        if parsed.get("cisco_ios_show_cdp_neighbors"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["cisco_ios_show_cdp_neighbors"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("Neighbor") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs
        if parsed.get("eltex_mes_show_lldp_neighbors_detail"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["eltex_mes_show_lldp_neighbors_detail"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs

        # D-Link LLDP neighbors
        if parsed.get("dlink_show_lldp_remote_ports_detail"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["dlink_show_lldp_remote_ports_detail"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs
        if parsed.get("dlink_show_lldp_remote_ports"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["dlink_show_lldp_remote_ports"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs

        # OSNOVA LLDP neighbors
        if parsed.get("osnova_show_lldp_neighbor_information"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["osnova_show_lldp_neighbor_information"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs

        # SNR LLDP neighbors (brief)
        if parsed.get("snr_show_lldp_neighbors_brief"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["snr_show_lldp_neighbors_brief"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs
        # ZES LLDP neighbors (brief)
        if parsed.get("zes_show_lldp_neighbors_brief"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["zes_show_lldp_neighbors_brief"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs
        if parsed.get("nis_show_lldp_neighbors"):
            ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
            for row in parsed["nis_show_lldp_neighbors"]:
                if_name = str(row.get("LocalInterface") or "").strip()
                peer_name = _short(str(row.get("NeighborName") or "").strip())
                peer_if = str(row.get("NeighborPort") or "").strip()
                if if_name and peer_name:
                    ifs.append({
                        "name": if_name,
                        "peer": {"hostname": peer_name, "interface": peer_if},
                        "speed": None,
                        "desc": None,
                    })
            if ifs:
                device["interfaces"] = ifs

        # Interfaces from NIS/ZES/SNR running-config (no peers)
        for key in ("nis_running_config_interfaces", "zes_running_config_interfaces", "snr_running_config_interfaces"):
            if parsed.get(key):
                ifs: List[Dict[str, Any]] = device.get("interfaces", []) or []
                for row in parsed[key]:
                    n = str(row.get("Interface") or "").strip()
                    if n:
                        ifs.append({"name": n, "peer": {}, "speed": None, "desc": None})
                if ifs:
                    device["interfaces"] = ifs

        add_or_update(device)
        added += 1

    out_data = {"devices": devs}
    dump_json(out_inv, out_data, log)
    log.info("[MERGE] from_cli=%d, total=%d", added, len(devs))
    return added, len(devs)


def step_safety_inventory_from_raw(out_inv: Path, raw_dir: Path, log: logging.Logger) -> int:
    """If out_inv has empty devices, fill from data/raw/*.txt filenames (IP)."""
    try:
        cur = json.loads(out_inv.read_text(encoding="utf-8"))
    except Exception:
        cur = {}
    devices = cur.get("devices") if isinstance(cur, dict) else None
    if not devices:
        devices = []
        for f in sorted(raw_dir.glob("*.txt")):
            ip = f.stem
            devices.append({
                "hostname": ip,
                "mgmt_ip": ip,
                "vendor": "unknown",
                "role": "access",
                "site": "",
            })
        dump_json(out_inv, {"devices": devices}, log)
        log.info("[SAFETY] built %d devices from %s", len(devices), raw_dir)
        return len(devices)
    return len(devices)


def step_normalize(inv_path: Path, normalized_out: Path, log: logging.Logger) -> Tuple[int, int, int]:
    log.info("[STEP 4] NORMALIZE -> %s", normalized_out)
    inv = NormInventory.load(inv_path)
    norm = Normalizer(inv, log).run()
    payload = {
        "nodes": norm.nodes,
        "edges": norm.edges,
        "meta": {
            "warnings": norm.warnings,
            "stats": {"nodes": len(norm.nodes), "edges": len(norm.edges)},
        },
    }
    dump_json(normalized_out, payload, log)
    return len(norm.nodes), len(norm.edges), len(norm.warnings)


def step_render(cfg_path: Path, normalized_path: Path, out_mmd: Path, log: logging.Logger) -> None:
    log.info("[STEP 5] RENDER -> %s", out_mmd)
    rcfg = RenderConfig.load(cfg_path)
    norm = load_normalized(normalized_path)
    # Optionally hide isolated nodes (no edges) to improve readability
    try:
        if os.environ.get("HIDE_ISOLATED", "1") != "0":
            touched = {e.get("src") for e in norm.edges} | {e.get("dst") for e in norm.edges}
            before = len(norm.nodes)
            norm.nodes = {k: v for k, v in norm.nodes.items() if k in touched}
            after = len(norm.nodes)
            if before != after:
                log.info("[RENDER] hide_isolated: %d -> %d nodes", before, after)
    except Exception:
        pass
    writer = MermaidWriter(rcfg, norm, log)
    text = writer.render()
    # Force ELK renderer in Mermaid init for better layout if not already set
    try:
        if 'defaultRenderer' not in text:
            needle = '"flowchart": {"htmlLabels": true, "curve": "basis"}'
            repl = '"flowchart": {"htmlLabels": true, "curve": "basis", "defaultRenderer": "elk"}'
            if needle in text:
                text = text.replace(needle, repl, 1)
    except Exception:
        pass
    out_mmd.parent.mkdir(parents=True, exist_ok=True)
    out_mmd.write_text(text, encoding="utf-8")
    log.info("Wrote %s", out_mmd)


# -----------------------------
# CLI
# -----------------------------

def default_paths(root: Path) -> Dict[str, Path]:
    cfg = root / "config" / "config.json"
    logs_dir = root / "data" / "output" / "logs"
    parsed = logs_dir / "parsed_textfsm.json"
    normalized = logs_dir / "normalized.json"
    out_mmd = root / "data" / "output" / "network.mmd"
    base_inv = root / "data" / "input" / "inventory.json"
    merged_inv = root / "data" / "input" / "inventory.merged.json"
    cli_dir = root / "data" / "input" / "cli"
    raw_dir = root / "data" / "raw"
    return {
        "config": cfg,
        "logs_dir": logs_dir,
        "parsed": parsed,
        "normalized": normalized,
        "out_mmd": out_mmd,
        "base_inv": base_inv,
        "merged_inv": merged_inv,
        "cli_dir": cli_dir,
        "raw_dir": raw_dir,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mermaid NetDocs pipeline runner")
    p.add_argument("--config", type=Path, help="Path to config.json (defaults to config/config.json)")
    p.add_argument("--env", type=Path, help="Path to .env file to load")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--log-file", type=Path, help="Optional log file to write duplicate logs")
    p.add_argument("--steps", default="collect,parse,split,merge,safety,normalize,render",
                   help="Comma-separated steps: collect,parse,split,merge,safety,normalize,render")
    # collect options
    p.add_argument("--targets", nargs="*", default=[], help="Targets (IPs/hosts)")
    p.add_argument("--cidr", nargs="*", default=[], help="CIDR subnets to scan")
    p.add_argument("--max-workers", type=int, default=int(os.environ.get("MAX_WORKERS", "32")))
    p.add_argument("--tcp-workers", type=int, default=int(os.environ.get("TCP_WORKERS", "64")))
    p.add_argument("--tcp-timeout", type=float, default=float(os.environ.get("TCP_TIMEOUT", "0.8")))
    p.add_argument("--conn-timeout", type=float, default=float(os.environ.get("CONNECT_TIMEOUT", "3")))
    p.add_argument("--auth-timeout", type=float, default=float(os.environ.get("AUTH_TIMEOUT", "12")))
    # parse options
    p.add_argument("--parse-workers", type=int, help="Workers for TextFSM parsing (env TEXTFSM_WORKERS)")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    log = setup_logger(args.log_level, args.log_file)
    root = project_root_from_here()
    dpaths = default_paths(root)

    cfg_path: Path = args.config or dpaths["config"]
    logs_dir: Path = dpaths["logs_dir"]
    parsed_path: Path = dpaths["parsed"]
    normalized_path: Path = dpaths["normalized"]
    out_mmd: Path = dpaths["out_mmd"]
    base_inv: Path = dpaths["base_inv"]
    merged_inv: Path = dpaths["merged_inv"]
    cli_dir: Path = dpaths["cli_dir"]
    raw_dir: Path = dpaths["raw_dir"]

    # Load .env and export to os.environ
    if args.env:
        env_vals = load_env_file(args.env, log)
        for k, v in env_vals.items():
            os.environ[k] = v

    ensure_dirs([logs_dir, out_mmd.parent, cli_dir, raw_dir])

    # Apply parse workers if provided
    if getattr(args, "parse_workers", None):
        os.environ["TEXTFSM_WORKERS"] = str(int(args.parse_workers))

    steps = [s.strip().lower() for s in (args.steps or "").split(",") if s.strip()]
    ordered = ["collect", "parse", "split", "merge", "safety", "normalize", "render"]
    plan = [s for s in ordered if s in steps]
    total = len(plan)
    done = 0
    if total > 0:
        log.info("Steps: %s", ", ".join(plan))
        log.info(progress_bar(done, total))

    try:
        for s in plan:
            log.info("Start: %s", s)
            if s == "collect":
                step_collect(args, LoaderConfig.load(cfg_path), logs_dir, log)
            elif s == "parse":
                step_textfsm_parse(cfg_path, base_inv, parsed_path, log)
            elif s == "split":
                step_split_cli(parsed_path, cli_dir, log)
            elif s == "merge":
                step_merge_inventory(base_inv, cli_dir, merged_inv, log)
            elif s == "safety":
                step_safety_inventory_from_raw(merged_inv, raw_dir, log)
            elif s == "normalize":
                inv_for_norm = merged_inv if merged_inv.exists() else base_inv
                step_normalize(inv_for_norm, normalized_path, log)
            elif s == "render":
                step_render(cfg_path, normalized_path, out_mmd, log)
            done += 1
            log.info("Done: %s", s)
            log.info(progress_bar(done, total))

        log.info("Pipeline OK")
        return 0
    except Exception as e:
        log.error("Pipeline error: %s", e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
