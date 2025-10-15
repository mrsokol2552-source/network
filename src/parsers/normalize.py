# -*- coding: utf-8 -*-
"""
normalize.py — унификация инвентаря и (при наличии) результатов TextFSM
в единый нормализованный граф для рендерера Mermaid.

Вход:
- inventory.json (см. data/input/inventory.json)
- (опционально) parsed_textfsm.json из шага textfsm_loader.py

Выход (в памяти) структура:
{
  "nodes": {
    "<hostname>": {
      "hostname": "...",
      "site": "DEN",
      "role": "core|dist|access|wan|dmz|mgmt",
      "vendor": "cisco_ios|eltex_mes|...",
      "model": "C9200-24T",
      "mgmt_ip": "10.10.0.1",
      "class": "core|dist|access|wan|dmz|mgmt",
      "labels": {
        "primary": "DEN-CORE-10-20-03\\n10.10.0.1\\nC9200-24T",
        "extra": []
      }
    },
    ...
  },
  "edges": [
    {
      "src": "DEN-CORE-10-20-03", "src_intf": "Gi1/0/1",
      "dst": "DEN-ACC-82-99-77", "dst_intf": "Gi0/25",
      "speed": "1G", "desc": "Uplink to ACCESS",
      "label": "Gi1/0/1 | 1G | Uplink to ACCESS",
      "layer": "L2|L3",
      "vlans": [10, 20],
      "ip": null
    },
    ...
  ],
  "meta": {
    "warnings": [],
    "stats": { "nodes": N, "edges": M }
  }
}

Также подготавливаем сортировку (стабильный вывод) и усечение длинных подписей.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# YAML больше не используется; инвентарь читаем как JSON


# -----------------------------
# Вспомогательные нормализаторы
# -----------------------------

ROLE_ORDER = ["core", "dist", "access", "wan", "dmz", "mgmt", "wifi"]

def zone_from_hostname(hostname: str) -> str | None:
    try:
        parts = (hostname or "").split("-")
        for tok in parts[1:]:
            if tok.isdigit() and 1 <= len(tok) <= 4:
                return tok
    except Exception:
        return None
    return None

def role_to_class(role: str) -> str:
    r = (role or "").lower()
    if r in ROLE_ORDER:
        return r
    return "access"

_SPEED_PAT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(g|m|k)?", re.I)

def normalize_speed(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    m = _SPEED_PAT.match(val)
    if not m:
        return val.strip()
    num, unit = m.groups()
    unit = (unit or "").lower()
    if unit in ("g", ""):
        # если без указания — считаем G
        return f"{num}G"
    if unit == "m":
        return f"{num}M"
    if unit == "k":
        return f"{num}K"
    return val.strip()

def truncate(s: Optional[str], limit: int = 80) -> Optional[str]:
    if not s:
        return s
    s = s.strip()
    return s if len(s) <= limit else s[: max(0, limit - 1)] + "…"

_INTF_NUM_PAT = re.compile(r"(\d+)")
def _natkey(text: str) -> List[Any]:
    """Натуральная сортировка: 'Gi1/0/10' > ['Gi', 1, '/', 0, '/', 10]"""
    parts: List[Any] = []
    buff = ""
    for ch in text:
        if ch.isdigit():
            if buff:
                parts.append(buff)
                buff = ""
            # накапливаем число
            num = ch
            continue
        # если встретили не цифру — закрыть предыдущее число (если было)
        if buff.isdigit():
            parts.append(int(buff))
            buff = ""
        buff += ch
    # закрыть буфер
    if buff:
        parts.append(int(buff) if buff.isdigit() else buff)
    return parts

def iface_sort_key(name: str) -> Tuple:
    if not name:
        return tuple()
    # Нормализуем популярные префиксы
    pref = name
    pref = pref.replace("Ethernet", "Et").replace("FastEthernet", "Fa")
    pref = pref.replace("GigabitEthernet", "Gi").replace("TenGigabitEthernet", "Te")
    pref = pref.replace("Port-Channel", "Po").replace("PortChannel", "Po").replace("Bundle-Ether", "BE")
    return tuple(_natkey(pref))

def vlan_label(v: Dict[str, Any]) -> str:
    vid = v.get("id")
    name = v.get("name")
    return f"VLAN {vid} — {name}" if name else f"VLAN {vid}"

def primary_node_label(hostname: str, mgmt_ip: Optional[str], model: Optional[str]) -> str:
    parts = [hostname]
    if mgmt_ip:
        parts.append(mgmt_ip)
    if model:
        parts.append(model)
    return "\\n".join(parts)


# -----------------------------
# Загрузка исходных данных
# -----------------------------

@dataclass
class Device:
    hostname: str
    site: Optional[str]
    role: Optional[str]
    vendor: Optional[str]
    platform: Optional[str]
    model: Optional[str]
    mgmt_ip: Optional[str]
    interfaces: List[Dict[str, Any]] = field(default_factory=list)
    vlans: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class Inventory:
    devices: Dict[str, Device]

    @staticmethod
    def load(path: Path) -> "Inventory":
        raw = json.loads(path.read_text(encoding="utf-8"))
        devs: Dict[str, Device] = {}
        for d in raw.get("devices", []):
            hostname = str(d.get("hostname", "")).strip()
            if not hostname:
                continue
            devs[hostname] = Device(
                hostname=hostname,
                site=d.get("site"),
                role=d.get("role"),
                vendor=d.get("vendor"),
                platform=d.get("platform"),
                model=d.get("model"),
                mgmt_ip=str(d.get("mgmt_ip")) if d.get("mgmt_ip") is not None else None,
                interfaces=d.get("interfaces", []) or [],
                vlans=d.get("vlans", []) or [],
            )
        return Inventory(devices=devs)


# -----------------------------
# Нормализация → граф
# -----------------------------

@dataclass
class Normalized:
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

class Normalizer:
    def __init__(self, inventory: Inventory, logger: Optional[logging.Logger] = None):
        self.inv = inventory
        self.log = logger or logging.getLogger("normalize")

    def run(self) -> Normalized:
        out = Normalized()

        # 1) Узлы
        for hn, d in self.inv.devices.items():
            role = (d.role or "access").lower()
            # Detect Wi-Fi class by role or model/name hints
            cls = role_to_class(role)
            mdl = (d.model or "").lower()
            if cls == "access":
                if role == "wifi" or "wifi" in mdl or " ap" in (" " + mdl) or "air" in mdl:
                    cls = "wifi"
            node = {
                "hostname": hn,
                "site": d.site,
                "zone": zone_from_hostname(hn),
                "role": role,
                "vendor": d.vendor,
                "platform": d.platform,
                "model": d.model,
                "mgmt_ip": d.mgmt_ip,
                "class": cls,
                "labels": {
                    "primary": primary_node_label(hn, d.mgmt_ip, d.model),
                    "extra": [],
                },
            }
            out.nodes[hn] = node

        # 2) Рёбра (по inventory.interfaces + peer)
        for hn, d in self.inv.devices.items():
            for itf in sorted(d.interfaces, key=lambda x: iface_sort_key(str(x.get("name", "")))):
                name = str(itf.get("name", "")).strip()
                if not name:
                    continue
                speed = normalize_speed(itf.get("speed"))
                desc = itf.get("desc")
                peer = itf.get("peer") or {}
                peer_hn = (peer.get("hostname") or "").strip()
                peer_if = (peer.get("interface") or "").strip()

                # Подпись ребра
                parts = [name or ""]
                parts.append(speed or "")
                parts.append(desc or "")
                label = " | ".join([p for p in parts if p]).strip()
                label = truncate(label, 80)

                edge = {
                    "src": hn, "src_intf": name or None,
                    "dst": peer_hn or None, "dst_intf": peer_if or None,
                    "speed": speed,
                    "desc": desc,
                    "label": label if label else None,
                    "layer": "L2",   # по умолчанию считаем L2; L3 уточним позже из TextFSM/интерфейсных IP
                    "vlans": [],
                    "ip": None,
                }

                # Если нет пира — допустим одностороннюю грань (для хоста/провайдера/подвисающих портов)
                if not peer_hn:
                    out.warnings.append(f"edge_without_peer:{hn}:{name}")
                else:
                    # Убедимся, что пиер существует в узлах; если нет — тоже варн
                    if peer_hn not in out.nodes:
                        out.warnings.append(f"peer_not_in_inventory:{hn}:{name}->{peer_hn}")

                out.edges.append(edge)

        # 3) VLAN → привяжем summary к узлам (для подписи)
        for hn, d in self.inv.devices.items():
            if not d.vlans:
                continue
            labels = [vlan_label(v) for v in sorted(d.vlans, key=lambda v: int(v.get("id", 0)))]
            # не засоряем primary; положим в extra
            extra = out.nodes[hn]["labels"]["extra"]
            # до 5 штук для читаемости (остальные скрываем)
            for txt in labels[:5]:
                extra.append(truncate(txt, 64))
            if len(labels) > 5:
                out.nodes[hn]["labels"]["extra"].append(f"+{len(labels)-5} VLANs")

        # 4) Стабильная сортировка рёбер
        def edge_key(e: Dict[str, Any]) -> Tuple:
            return (
                ((self.inv.devices.get(e["src"]).site or "") if self.inv.devices.get(e["src"]) else ""),
                ROLE_ORDER.index(out.nodes[e["src"]]["role"]) if e["src"] in out.nodes and out.nodes[e["src"]]["role"] in ROLE_ORDER else 99,
                e["src"],
                iface_sort_key(e.get("src_intf") or ""),
                e.get("dst") or "",
                iface_sort_key(e.get("dst_intf") or ""),
            )
        out.edges.sort(key=edge_key)

        # 5) Итоговая статистика
        return out


# -----------------------------
# CLI-утилита для шага конвейера
# -----------------------------

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("normalize")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

def _default_paths(root: Path) -> Tuple[Path, Path, Path]:
    """Возвращает (inventory.json, normalized.json, logs_dir)"""
    inv = root / "data" / "input" / "inventory.json"
    out = root / "data" / "output" / "logs" / "normalized.json"
    logs_dir = root / "data" / "output" / "logs"
    return inv, out, logs_dir

if __name__ == "__main__":
    """
    Запуск:
      python -m src.parsers.normalize

    Результат:
      data/output/logs/normalized.json
    """
    log = _setup_logger()
    project_root = Path(__file__).resolve().parents[2]  # .../src/parsers -> корень
    inv_path, out_path, logs_dir = _default_paths(project_root)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        inv = Inventory.load(inv_path)
        norm = Normalizer(inv, log).run()

        payload = {
            "nodes": norm.nodes,
            "edges": norm.edges,
            "meta": {
                "warnings": norm.warnings,
                "stats": {"nodes": len(norm.nodes), "edges": len(norm.edges)},
            },
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Готово: %s (nodes=%d, edges=%d, warnings=%d)",
                 out_path, len(norm.nodes), len(norm.edges), len(norm.warnings))
    except Exception as e:
        log.error("Фатальная ошибка: %s", e)
        raise
