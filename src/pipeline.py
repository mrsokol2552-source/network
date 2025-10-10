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

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("pipeline")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
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
    # Allow .env overrides already applied to os.environ by caller
    subprocess.run(cmd, check=False, cwd=str(project_root_from_here()), env=env)


def step_textfsm_parse(cfg_path: Path, inv_path: Path, parsed_out: Path, log: logging.Logger) -> None:
    log.info("[STEP 2] PARSE CLI (TextFSM -> parsed_textfsm.json)")
    cfg = LoaderConfig.load(cfg_path)
    inv = LoaderInventory.load(inv_path)
    parser = TextFSMParser(cfg, inv, log)
    data = parser.parse_all()
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

    known = {str((d.get("hostname") or d.get("mgmt_ip") or "").strip()) for d in devs if isinstance(d, dict)}
    rx = re.compile(r'(?:^|[^0-9])(\d{1,3}(?:\.\d{1,3}){3})(?:[^0-9]|$)')
    added = 0
    for fp in sorted(cli_dir.glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = fp.name
        m = rx.search(name)
        ip = m.group(1) if m else ""
        host = (d.get("hostname") or d.get("host") or ip or "").strip()
        mgmt = str(d.get("mgmt_ip") or d.get("ip") or ip or "").strip()
        key = host or mgmt
        if key and key not in known:
            devs.append({"hostname": host or mgmt, "mgmt_ip": mgmt})
            known.add(key)
            added += 1

    out_data = {"devices": devs}
    dump_json(out_inv, out_data, log)
    log.info("[MERGE] added_from_cli=%d, total=%d", added, len(devs))
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
    writer = MermaidWriter(rcfg, norm, log)
    text = writer.render()
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
    p.add_argument("--steps", default="collect,parse,split,merge,safety,normalize,render",
                   help="Comma-separated steps: collect,parse,split,merge,safety,normalize,render")
    # collect options
    p.add_argument("--targets", nargs="*", default=[], help="Targets (IPs/hosts)")
    p.add_argument("--cidr", nargs="*", default=[], help="CIDR subnets to scan")
    p.add_argument("--max-workers", type=int, default=int(os.environ.get("MAX_WORKERS", "32")))
    p.add_argument("--tcp-timeout", type=float, default=float(os.environ.get("TCP_TIMEOUT", "0.8")))
    p.add_argument("--conn-timeout", type=float, default=float(os.environ.get("CONNECT_TIMEOUT", "3")))
    p.add_argument("--auth-timeout", type=float, default=float(os.environ.get("AUTH_TIMEOUT", "12")))
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    log = setup_logger(args.log_level)
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
