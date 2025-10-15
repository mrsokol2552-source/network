# -*- coding: utf-8 -*-
"""
textfsm_loader.py вЂ” Р»РѕР°РґРµСЂ TextFSM-С€Р°Р±Р»РѕРЅРѕРІ Рё РїР°СЂСЃРµСЂ СЃС‹СЂС‹С… CLI РІ РЅРѕСЂРјР°Р»РёР·РѕРІР°РЅРЅС‹Р№ JSON.

РќР°Р·РЅР°С‡РµРЅРёРµ:
- Р—Р°РіСЂСѓР·РёС‚СЊ С€Р°Р±Р»РѕРЅС‹ TextFSM СЃРѕРіР»Р°СЃРЅРѕ config.json (vendors.*.textfsm_glob).
- РџСЂРёРјРµРЅРёС‚СЊ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‰РёРµ С€Р°Р±Р»РѕРЅС‹ Рє СЃС‹СЂС‹Рј CLI-С„Р°Р№Р»Р°Рј РёР· inventory.json (cli_files[]).
- Р’РµСЂРЅСѓС‚СЊ СЃС‚СЂСѓРєС‚СѓСЂРёСЂРѕРІР°РЅРЅС‹Р№ JSON РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµР№ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё/СЂРµРЅРґРµСЂР°.

РћР¶РёРґР°РµРјС‹Рµ С„Р°Р№Р»С‹:
- config/config.json
- data/input/inventory.json
- templates/textfsm/<vendor>/*.template
- data/input/cli/<Р¤РђР™Р›Р«_РР—_inventory.yml>

Р’С‹С…РѕРґ (РІ РїР°РјСЏС‚Рё): dict:
{
  "hosts": {
    "<hostname>": {
      "vendor": "cisco_ios" | "eltex_mes" | ...,
      "raw_files": ["show_*.txt", ...],
      "parsed": {
         "<template_stem>": [
            {"Field1": "Val1", "Field2": "Val2", ...},
            ...
         ],
         ...
      },
      "errors": [ "message", ... ]
    },
    ...
  },
  "meta": {
    "templates_total": N,
    "errors": [ ... ]
  }
}

РџСЂРёРјРµС‡Р°РЅРёСЏ:
- РњС‹ РЅРµ В«СѓРіР°РґС‹РІР°РµРјВ» СЃРѕРѕС‚РІРµС‚СЃС‚РІРёРµ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ С€Р°Р±Р»РѕРЅР° Рє РєРѕРЅРєСЂРµС‚РЅРѕР№ РєРѕРјР°РЅРґРµ вЂ” РїСЂРёРјРµРЅСЏРµРј РІСЃРµ С€Р°Р±Р»РѕРЅС‹ РІРµРЅРґРѕСЂР°, Р° Р·Р°РїРёСЃРё,
  РіРґРµ РЅРёС‡РµРіРѕ РЅРµ РЅР°Р№РґРµРЅРѕ, РїСЂРѕСЃС‚Рѕ РґР°СЋС‚ РїСѓСЃС‚РѕР№ СЃРїРёСЃРѕРє. РќР° СЃР»РµРґСѓСЋС‰РµРј СЌС‚Р°РїРµ РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ РјР°РїРїРёРЅРі С€Р°Р±Р»РѕРЅРѕРІ Рє С„Р°Р№Р»Р°Рј.
- РћС€РёР±РєРё РЅРµ С„Р°С‚Р°Р»СЊРЅС‹: Р°РєРєСѓРјСѓР»РёСЂСѓРµРј Рё РїСЂРѕРґРѕР»Р¶Р°РµРј.
"""

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import ipaddress

# Р’РЅРµС€РЅРёРµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё
# YAML Р±РѕР»СЊС€Рµ РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ; config Рё inventory С‡РёС‚Р°РµРј РєР°Рє JSON

try:
    import textfsm
except Exception as e:  # pragma: no cover
    raise RuntimeError("РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ Р·Р°РІРёСЃРёРјРѕСЃС‚СЊ 'textfsm'. РЈСЃС‚Р°РЅРѕРІРё: pip install textfsm") from e


# -----------------------------
# РљРѕРЅС„РёРі Рё РёРЅРІРµРЅС‚Р°СЂСЊ вЂ” Р»С‘РіРєРёРµ DTO
# -----------------------------

@dataclass
class VendorSpec:
    name: str
    textfsm_glob: str
    platform_patterns: List[str]


@dataclass
class Config:
    root: Path
    cli_dir: Path
    vendors: Dict[str, VendorSpec]

    @staticmethod
    def load(path: Path) -> "Config":
        raw = json.loads(path.read_text(encoding="utf-8"))
        root = path.parent.parent  # .../config -> РєРѕСЂРµРЅСЊ РїСЂРѕРµРєС‚Р°
        cli_dir = (root / raw["paths"]["cli_dir"]).resolve()
        vendors: Dict[str, VendorSpec] = {}

        vraw = raw.get("vendors", {})
        for vname, vcfg in vraw.items():
            vendors[vname] = VendorSpec(
                name=vname,
                textfsm_glob=vcfg.get("textfsm_glob", ""),
                platform_patterns=vcfg.get("platform_patterns", []),
            )

        return Config(root=root, cli_dir=cli_dir, vendors=vendors)


@dataclass
class CliFilesEntry:
    hostname: str
    files: List[str]


@dataclass
class Device:
    hostname: str
    vendor: str | None


@dataclass
class Inventory:
    devices: Dict[str, Device]
    cli_files: Dict[str, CliFilesEntry]

    @staticmethod
    def load(path: Path) -> "Inventory":
        raw = json.loads(path.read_text(encoding="utf-8"))
        devices: Dict[str, Device] = {}
        for d in raw.get("devices", []):
            hostname = str(d.get("hostname", "")).strip()
            vendor = d.get("vendor")
            if hostname:
                devices[hostname] = Device(hostname=hostname, vendor=vendor)

        cli_files: Dict[str, CliFilesEntry] = {}
        for entry in raw.get("cli_files", []):
            hostname = str(entry.get("hostname", "")).strip()
            files = [str(f) for f in entry.get("files", [])]
            if hostname:
                cli_files[hostname] = CliFilesEntry(hostname=hostname, files=files)

        return Inventory(devices=devices, cli_files=cli_files)


# -----------------------------
# Р—Р°РіСЂСѓР·РєР° С€Р°Р±Р»РѕРЅРѕРІ
# -----------------------------

@dataclass
class CompiledTemplate:
    vendor: str
    path: Path
    stem: str
    fsm: textfsm.TextFSM


class TemplateLoader:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def load_vendor_templates(self, vendor: str) -> List[CompiledTemplate]:
        spec = self.config.vendors.get(vendor)
        if not spec:
            self.logger.warning("Р’РµРЅРґРѕСЂ %s РЅРµ Р·Р°РґР°РЅ РІ config.json->vendors", vendor)
            return []

        pattern = spec.textfsm_glob
        if not pattern:
            self.logger.warning("Р”Р»СЏ РІРµРЅРґРѕСЂР° %s РЅРµ Р·Р°РґР°РЅ textfsm_glob", vendor)
            return []

        glob_root = self.config.root  # glob РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅС‹Р№ РѕС‚ РєРѕСЂРЅСЏ РїСЂРѕРµРєС‚Р°
        matches = sorted(glob_root.glob(pattern))
        compiled: List[CompiledTemplate] = []

        for tpath in matches:
            try:
                with tpath.open("r", encoding="utf-8") as fh:
                    fsm = textfsm.TextFSM(fh)
                compiled.append(
                    CompiledTemplate(
                        vendor=vendor,
                        path=tpath,
                        stem=tpath.stem,
                        fsm=fsm,
                    )
                )
            except Exception as e:
                self.logger.error("РћС€РёР±РєР° РєРѕРјРїРёР»СЏС†РёРё С€Р°Р±Р»РѕРЅР° %s: %s", tpath, e)

        self.logger.info("Р—Р°РіСЂСѓР¶РµРЅРѕ С€Р°Р±Р»РѕРЅРѕРІ: vendor=%s count=%d", vendor, len(compiled))
        return compiled


# -----------------------------
# РћСЃРЅРѕРІРЅРѕР№ РїР°СЂСЃРµСЂ
# -----------------------------

class TextFSMParser:
    def __init__(self, config: Config, inventory: Inventory, logger: logging.Logger | None = None):
        self.config = config
        self.inventory = inventory
        self.log = logger or logging.getLogger("textfsm_loader")
        self._cache_vendor_templates: Dict[str, List[CompiledTemplate]] = {}
        self.meta_errors: List[str] = []

    def _guess_vendor(self, sample: str) -> str:
        s = (sample or "").lower()
        for v, spec in self.config.vendors.items():
            for patt in (spec.platform_patterns or []):
                if str(patt).lower() in s:
                    return v
        if "routeros" in s or "mikrotik" in s:
            return "mikrotik"
        if "eltex" in s or " mes" in s:
            return "eltex_mes"
        if "huawei" in s or " vrp" in s:
            return "huawei_vrp"
        if "d-link" in s or " dgs" in s or " des-" in s:
            return "dlink"
        if "qtech" in s or " qsw" in s:
            return "qtech"
        return "cisco_ios"

    # Vendor hints support (config/collect/vendor_hints.json)
    def _load_vendor_hints(self) -> List[Dict[str, str]]:
        p = self.config.root / "config" / "collect" / "vendor_hints.json"
        try:
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                items = raw.get("ranges") if isinstance(raw, dict) else raw
                return [i for i in (items or []) if isinstance(i, dict) and i.get("cidr") and i.get("vendor")]
        except Exception:
            return []
        return []

    def _vendor_hint_for_ip(self, ip: str) -> str | None:
        hints = getattr(self, "_vendor_hints_cache", None)
        if hints is None:
            hints = self._vendor_hints_cache = self._load_vendor_hints()
        try:
            addr = ipaddress.ip_address(ip)
        except Exception:
            return None
        for item in hints:
            try:
                if addr in ipaddress.ip_network(str(item.get("cidr")), strict=False):
                    return str(item.get("vendor"))
            except Exception:
                continue
        return None

    def _templates_for_vendor(self, vendor: str) -> List[CompiledTemplate]:
        if vendor not in self._cache_vendor_templates:
            loader = TemplateLoader(self.config, self.log)
            self._cache_vendor_templates[vendor] = loader.load_vendor_templates(vendor)
        return self._cache_vendor_templates[vendor]

    def _read_cli_text(self, rel_path: str) -> Tuple[str, Path | None]:
        """Р§РёС‚Р°РµС‚ CLI-С„Р°Р№Р» РёР· paths.cli_dir. Р’РѕР·РІСЂР°С‰Р°РµС‚ (text, full_path|None)."""
        full = (self.config.cli_dir / rel_path).resolve()
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
            return text, full
        except Exception as e:
            self.log.error("РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ CLI-С„Р°Р№Р» %s: %s", full, e)
            self.meta_errors.append(f"read_error:{rel_path}:{e}")
            return "", None

    def parse_all(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "hosts": {},
            "meta": {"templates_total": 0, "errors": self.meta_errors},
        }

        # --- Fallback: если inventory пуст, собрать устройства прямо из cli_dir (включая подкаталоги) ---
        if not self.inventory.devices:
            for p in sorted(self.config.cli_dir.rglob("*.txt")):
                try:
                    head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
                except Exception:
                    head = ""
                m = re.search(r'(?m)^\s*hostname\s+([\w\-.]+)', head)
                hostname = m.group(1) if m else p.stem
                vendor = self._vendor_hint_for_ip(p.stem) or self._guess_vendor(head)
                # зарегистрировать устройство и список файлов
                self.inventory.devices[hostname] = Device(hostname=hostname, vendor=vendor)
                try:
                    rel = str(p.relative_to(self.config.cli_dir))
                except Exception:
                    rel = p.name
                self.inventory.cli_files[hostname] = CliFilesEntry(hostname=hostname, files=[rel])
        # --- /Fallback ---

        # РїРѕСЃС‡РёС‚Р°С‚СЊ РѕР±С‰РµРµ С‡РёСЃР»Рѕ С€Р°Р±Р»РѕРЅРѕРІ (РґР»СЏ РёРЅС„Рѕ)
        total_templates = 0
        seen_vendors: set[str] = set(d.vendor for d in self.inventory.devices.values() if d.vendor)
        for v in seen_vendors:
            total_templates += len(self._templates_for_vendor(v))
        result["meta"]["templates_total"] = total_templates

        for hostname, device in self.inventory.devices.items():
            host_entry = {
                "vendor": device.vendor,
                "raw_files": [],
                "parsed": {},
                "errors": [],
            }

            # РєР°РєРёРµ С„Р°Р№Р»С‹ РЅР°Рј РЅСѓР¶РЅРѕ СЂР°Р·РѕР±СЂР°С‚СЊ РґР»СЏ СЌС‚РѕРіРѕ С…РѕСЃС‚Р°
            cf = self.inventory.cli_files.get(hostname)
            if not cf or not cf.files:
                # СЌС‚Рѕ РЅРµ РѕС€РёР±РєР° вЂ” СѓСЃС‚СЂРѕР№СЃС‚РІРѕ РјРѕР¶РµС‚ Р·Р°РїРѕР»РЅСЏС‚СЊСЃСЏ РёР· inventory.json Р±РµР· CLI
                result["hosts"][hostname] = host_entry
                continue

            host_entry["raw_files"] = list(cf.files)

            # С€Р°Р±Р»РѕРЅС‹ РїРѕ РІРµРЅРґРѕСЂСѓ
            templates = self._templates_for_vendor(device.vendor or "")
            if not templates:
                msg = f"no_templates_for_vendor:{device.vendor}"
                self.log.warning("%s -> %s", hostname, msg)
                host_entry["errors"].append(msg)

            # С‡РёС‚Р°РµРј РєР°Р¶РґС‹Р№ CLI-С„Р°Р№Р» Рё РїСЂРѕРіРѕРЅСЏРµРј С‡РµСЂРµР· РІСЃРµ С€Р°Р±Р»РѕРЅС‹ РІРµРЅРґРѕСЂР°
            for rel_path in cf.files:
                cli_text, full_path = self._read_cli_text(rel_path)
                if not cli_text:
                    host_entry["errors"].append(f"empty_or_unreadable:{rel_path}")
                    continue

                for tpl in templates:
                    try:
                        # Р’Р°Р¶РЅРѕ: TextFSM РѕР±СЉРµРєС‚ РѕРґРЅРѕСЂР°Р·РѕРІС‹Р№, СЃРѕР·РґР°С‘Рј fresh instance РёР· С‚Р°Р±Р»РёС†С‹
                        # (РёРЅР°С‡Рµ РєСѓСЂСЃРѕСЂС‹ Рё СЃРѕСЃС‚РѕСЏРЅРёСЏ Р»РѕРјР°СЋС‚ РїРѕРІС‚РѕСЂРЅС‹Рµ РІС‹Р·РѕРІС‹)
                        with tpl.path.open("r", encoding="utf-8") as fh:
                            fresh_fsm = textfsm.TextFSM(fh)

                        records = fresh_fsm.ParseText(cli_text)  # List[List[str]]
                        if not records:
                            # РїСѓСЃС‚Рѕ вЂ” СЌС‚Рѕ РЅРѕСЂРјР°Р»СЊРЅРѕ, РїСЂРѕСЃС‚Рѕ РЅРёС‡РµРіРѕ РЅРµ РґРѕР±Р°РІР»СЏРµРј
                            continue

                        # РњР°РїРїРёРј РІ dict РїРѕ РёРјРµРЅР°Рј СЃС‚РѕР»Р±С†РѕРІ РёР· С€Р°Р±Р»РѕРЅР°
                        headers = [h.strip() for h in fresh_fsm.header]
                        dicts = [dict(zip(headers, row)) for row in records]

                        # РљР»СЋС‡ РґР»СЏ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ вЂ” stem С€Р°Р±Р»РѕРЅР° (СѓРЅРёРєР°Р»СЊРЅРѕ РІ СЂР°РјРєР°С… РІРµРЅРґРѕСЂР°)
                        bucket = host_entry["parsed"].setdefault(tpl.stem, [])
                        # РґРѕР±Р°РІРёРј РёСЃС‚РѕС‡РЅРёРє С„Р°Р№Р»Р° РґР»СЏ РєР°Р¶РґРѕР№ Р·Р°РїРёСЃРё:
                        for d in dicts:
                            d["_source_file"] = str(full_path) if full_path else rel_path
                            d["_template"] = tpl.path.name
                            bucket.append(d)

                    except Exception as e:
                        emsg = f"parse_error:{rel_path}:{tpl.path.name}:{e}"
                        self.log.error("%s -> %s", hostname, emsg)
                        host_entry["errors"].append(emsg)

            result["hosts"][hostname] = host_entry

        return result

    def parse_all_fast(self) -> Dict[str, Any]:
        """Parallel version of parse_all() processing hosts concurrently.
        Number of workers is controlled via env TEXTFSM_WORKERS (default: cpu_count or 4, capped at 32).
        """
        result: Dict[str, Any] = {
            "hosts": {},
            "meta": {"templates_total": 0, "errors": self.meta_errors},
        }

        # Fallback to discover devices from CLI dir if inventory missing (recursive)
        if not self.inventory.devices:
            for p in sorted(self.config.cli_dir.rglob("*.txt")):
                try:
                    head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
                except Exception:
                    head = ""
                m = re.search(r'(?m)^\s*hostname\s+([\w\-.]+)', head)
                hostname = m.group(1) if m else p.stem
                vendor = self._vendor_hint_for_ip(p.stem) or self._guess_vendor(head)
                self.inventory.devices[hostname] = Device(hostname=hostname, vendor=vendor)
                try:
                    rel = str(p.relative_to(self.config.cli_dir))
                except Exception:
                    rel = p.name
                self.inventory.cli_files[hostname] = CliFilesEntry(hostname=hostname, files=[rel])

        # Count templates for meta
        total_templates = 0
        seen_vendors: set[str] = set(d.vendor for d in self.inventory.devices.values() if d.vendor)
        for v in seen_vendors:
            total_templates += len(self._templates_for_vendor(v))
        result["meta"]["templates_total"] = total_templates

        def _process_host(hostname: str, device: Device) -> tuple[str, Dict[str, Any]]:
            host_entry: Dict[str, Any] = {
                "vendor": device.vendor,
                "raw_files": [],
                "parsed": {},
                "errors": [],
            }
            cf = self.inventory.cli_files.get(hostname)
            if not cf or not cf.files:
                return hostname, host_entry
            host_entry["raw_files"] = list(cf.files)
            templates = self._templates_for_vendor(device.vendor or "")
            if not templates:
                msg = f"no_templates_for_vendor:{device.vendor}"
                self.log.warning("%s -> %s", hostname, msg)
                host_entry["errors"].append(msg)
            for rel_path in cf.files:
                cli_text, full_path = self._read_cli_text(rel_path)
                if not cli_text:
                    host_entry["errors"].append(f"empty_or_unreadable:{rel_path}")
                    continue
                for tpl in templates:
                    try:
                        with tpl.path.open("r", encoding="utf-8") as fh:
                            fresh_fsm = textfsm.TextFSM(fh)
                        records = fresh_fsm.ParseText(cli_text)
                        if not records:
                            continue
                        headers = [h.strip() for h in fresh_fsm.header]
                        dicts = [dict(zip(headers, row)) for row in records]
                        bucket = host_entry["parsed"].setdefault(tpl.stem, [])
                        for d in dicts:
                            d["_source_file"] = str(full_path) if full_path else rel_path
                            d["_template"] = tpl.path.name
                            bucket.append(d)
                    except Exception as e:
                        emsg = f"parse_error:{rel_path}:{tpl.path.name}:{e}"
                        self.log.error("%s -> %s", hostname, emsg)
                        host_entry["errors"].append(emsg)
            return hostname, host_entry

        try:
            workers = int(os.environ.get("TEXTFSM_WORKERS", "0"))
        except Exception:
            workers = 0
        if workers <= 0:
            workers = min(32, (os.cpu_count() or 4))

        futures = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for hostname, device in self.inventory.devices.items():
                futures.append(ex.submit(_process_host, hostname, device))
            total = len(futures)
            done = 0
            for fut in as_completed(futures):
                try:
                    hn, entry = fut.result()
                    result["hosts"][hn] = entry
                except Exception as e:
                    self.log.error("host_task_error: %s", e)
                finally:
                    done += 1
                    if done % 10 == 0 or done == total:
                        self.log.info("textfsm_parse_progress: %d/%d", done, total)

        return result


# -----------------------------
# РЈС‚РёР»РёС‚Р° CLI (РїРѕ Р¶РµР»Р°РЅРёСЋ)
# -----------------------------

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("textfsm_loader")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    ch.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(ch)
    return logger


def _default_paths(root: Path) -> Tuple[Path, Path]:
    """Р’РѕР·РІСЂР°С‚ РїСѓС‚РµР№ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ: (config_path, inventory_path)"""
    return (root / "config" / "config.json", root / "data" / "input" / "inventory.json")


if __name__ == "__main__":
    """
    РџСЂРёРјРµСЂ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ:
      python -m src.parsers.textfsm_loader
    Р—Р°РїРёС€РµС‚ СЂРµР·СѓР»СЊС‚Р°С‚ РІ data/output/logs/parsed_textfsm.json
    """
    logger = _setup_logger()
    project_root = Path(__file__).resolve().parents[2]  # .../src/parsers -> РєРѕСЂРµРЅСЊ
    cfg_path, inv_path = _default_paths(project_root)

    try:
        cfg = Config.load(cfg_path)
        inv = Inventory.load(inv_path)
        parser = TextFSMParser(cfg, inv, logger)
        data = parser.parse_all()

        out_dir = (project_root / "data" / "output" / "logs")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "parsed_textfsm.json"
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Р“РѕС‚РѕРІРѕ: %s", out_file)
    except Exception as e:
        logger.error("Р¤Р°С‚Р°Р»СЊРЅР°СЏ РѕС€РёР±РєР°: %s", e)
        raise
