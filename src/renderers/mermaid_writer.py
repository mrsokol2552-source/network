# -*- coding: utf-8 -*-
"""
mermaid_writer.py вЂ” РіРµРЅРµСЂР°С†РёСЏ Mermaid (.mmd) РёР· РЅРѕСЂРјР°Р»РёР·РѕРІР°РЅРЅРѕРіРѕ РіСЂР°С„Р°.

Р’С…РѕРґ:
- config/config.json (render.*, paths.*)
- data/output/logs/normalized.json (РёР· normalize.py)

Р’С‹С…РѕРґ:
- data/output/network.mmd

РџРѕРґС‡РёРЅСЏРµС‚СЃСЏ РїСЂР°РІРёР»Р°Рј РёР· standards/mermaid_style.md:
- flowchart LR, elk renderer (РµСЃР»Рё РІРєР»СЋС‡С‘РЅ РІ СЃСЂРµРґРµ вЂ” РґРѕР±Р°РІР»СЏРµС‚СЃСЏ РѕС‚РґРµР»СЊРЅРѕ)
- РєР»Р°СЃСЃС‹ core/dist/access/wan/dmz/mgmt
- СЃС‚Р°Р±РёР»СЊРЅС‹Р№ РїРѕСЂСЏРґРѕРє СѓР·Р»РѕРІ/СЂС‘Р±РµСЂ
- РѕРїС†РёРѕРЅР°Р»СЊРЅС‹Рµ subgraph (РїРѕ site/role РІ РїСЂРѕСЃС‚РѕРј РІР°СЂРёР°РЅС‚Рµ вЂ” РїРѕ site)

РџСЂРёРјРµС‡Р°РЅРёРµ: htmlLabels=false, РїРѕСЌС‚РѕРјСѓ РїРµСЂРµРЅРѕСЃ СЃС‚СЂРѕРєРё вЂ” '\\n' РІ Р»РµР№Р±Р»Р°С….
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Tuple
import re

# YAML Р±РѕР»СЊС€Рµ РЅРµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ; РєРѕРЅС„РёРі С‡РёС‚Р°РµРј РєР°Рє JSON


# -----------------------------
# РљРѕРЅС„РёРі DTO
# -----------------------------

@dataclass
class RenderConfig:
    layout_engine: str            # "elk" | "dagre"
    flow_direction: str           # "LR" | "TD"
    use_subgraphs: bool
    label_verbosity: str          # "none" | "brief" | "full"
    show_ports: bool
    show_vlans: bool
    show_ips: bool
    font_size: str | None = None  # e.g. "18px"
    node_spacing: int | None = None
    rank_spacing: int | None = None
    diagram_padding: int | None = None


@dataclass
class PathsConfig:
    output_mermaid: Path
    standards_file: Path


@dataclass
class Config:
    render: RenderConfig
    paths: PathsConfig
    root: Path

    @staticmethod
    def load(path: Path) -> "Config":
        raw = json.loads(path.read_text(encoding="utf-8"))
        root = path.parent.parent  # .../config -> РєРѕСЂРµРЅСЊ
        r = raw.get("render", {})
        render = RenderConfig(
            layout_engine=r.get("layout_engine", "elk"),
            flow_direction=r.get("flow_direction", "LR"),
            use_subgraphs=bool(r.get("use_subgraphs", False)),
            label_verbosity=r.get("label_verbosity", "full"),
            show_ports=bool(r.get("show_ports", True)),
            show_vlans=bool(r.get("show_vlans", True)),
            show_ips=bool(r.get("show_ips", True)),
            font_size=r.get("font_size"),
            node_spacing=r.get("node_spacing"),
            rank_spacing=r.get("rank_spacing"),
            diagram_padding=r.get("diagram_padding"),
        )
        p = raw.get("paths", {})
        paths = PathsConfig(
            output_mermaid=(root / p.get("output_mermaid", "data/output/network.mmd")).resolve(),
            standards_file=(root / p.get("standards_file", "standards/mermaid_style.md")).resolve(),
        )
        return Config(render=render, paths=paths, root=root)


# -----------------------------
# РќРѕСЂРјР°Р»РёР·РѕРІР°РЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
# -----------------------------

@dataclass
class Normalized:
    nodes: Dict[str, Dict[str, Any]]
    edges: List[Dict[str, Any]]
    warnings: List[str]


def load_normalized(path: Path) -> Normalized:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Normalized(nodes=raw.get("nodes", {}),
                      edges=raw.get("edges", []),
                      warnings=raw.get("meta", {}).get("warnings", []))


# -----------------------------
# Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅС‹Рµ
# -----------------------------

ROLE_ORDER = ["core", "dist", "access", "wan", "dmz", "mgmt", "wifi"]

def role_order_idx(role: str) -> int:
    try:
        return ROLE_ORDER.index((role or "").lower())
    except ValueError:
        return 99

def stable_node_key(item: Tuple[str, Dict[str, Any]]) -> Tuple:
    hn, n = item
    return (str(n.get("site") or ""),
            role_order_idx(str(n.get("role") or "")),
            hn)

def esc(text: str) -> str:
    """РџСЂРѕСЃС‚РѕР№ СЌРєСЂР°РЅРёСЂРѕРІС‰РёРє РґР»СЏ Mermaid label (Р±РµР· htmlLabels)."""
    if text is None:
        return ""
    # Mermaid РЅРѕСЂРјР°Р»СЊРЅРѕ РїРµСЂРµРЅРѕСЃРёС‚ \n, СЌРєСЂР°РЅРёСЂСѓРµРј С‚РѕР»СЊРєРѕ РєР°РІС‹С‡РєРё
    return str(text).replace('"', '\\"')

def build_node_line(node_id: str, n: Dict[str, Any], cfg: Config) -> str:
    """
    РќРѕРґР° РїРµС‡Р°С‚Р°РµС‚СЃСЏ РєР°Рє:
    ID["DEN-CORE-10-20-03\n10.10.0.1\nC9200"]:::core
    """
    def safe_id(s: str) -> str:
        return re.sub(r"[^0-9A-Za-z_]", "_", s)
    primary = n.get("labels", {}).get("primary") or n.get("hostname") or node_id
    extras: List[str] = n.get("labels", {}).get("extra") or []
    # Р’ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ verbosity РјРѕР¶РЅРѕ СѓР±СЂР°С‚СЊ extras
    extra_text = ""
    if cfg.render.label_verbosity == "full" and extras:
        extra_text = "<br/>" + "<br/>".join(extras[:5])

    pp = primary.replace("\\n", "<br/>").replace("\n", "<br/>")
    label = esc(pp) + extra_text
    cls = (n.get("class") or "access").lower()
    return f'{safe_id(node_id)}["{label}"]:::{cls}'

def build_edge_line(e: Dict[str, Any]) -> str:
    """
    A -- "Gi1/0/1 | 1G | Uplink to ACCESS" --- B
    Р•СЃР»Рё РЅРµС‚ dst вЂ” СЂРёСЃСѓРµРј РІРёСЃСЏС‡РµРµ СЂРµР±СЂРѕ Рє Р°РЅРѕРЅРёРјРЅРѕР№ С‚РѕС‡РєРµ? Р’ Mermaid С‚Р°Рє Р»СѓС‡С€Рµ РЅРµ РґРµР»Р°С‚СЊ.
    Р’ РЅР°С€РµРј РєРѕРЅРІРµР№РµСЂРµ С‚Р°РєРёРµ СЂС‘Р±СЂР° РІСЃС‘ СЂР°РІРЅРѕ Р±СѓРґСѓС‚, РЅРѕ Mermaid С‚СЂРµР±СѓРµС‚ РІР°Р»РёРґРЅРѕРіРѕ dst.
    РџРѕСЌС‚РѕРјСѓ РїСЂРѕРїСѓСЃРєР°РµРј СЂС‘Р±СЂР° Р±РµР· dst.
    """
    def safe_id(s: str) -> str:
        return re.sub(r"[^0-9A-Za-z_]", "_", s)
    src = e.get("src")
    dst = e.get("dst")
    if not src or not dst:
        return ""  # РїСЂРѕРїСѓСЃС‚РёРј
    # Печатаем порты у каждого конца, чтобы различать параллельные линki
    s_if = (e.get("src_intf") or "").strip()
    d_if = (e.get("dst_intf") or "").strip()
    label = ""
    if s_if or d_if:
        if s_if and d_if:
            label = f'({s_if}) <-> ({d_if})'
        elif s_if:
            label = f'({s_if})'
        else:
            label = f'({d_if})'
    if label:
        return f'{safe_id(src)} -- "{esc(label)}" --- {safe_id(dst)}'
    return f"{safe_id(src)} --- {safe_id(dst)}"

def class_defs() -> str:
    return (
        "classDef core   stroke-width:2px,stroke:#1f77b4,fill:#e6f1fb,color:#111,font-size:40px;\n"
        "classDef dist   stroke-width:2px,stroke:#2ca02c,fill:#eaf7ea,color:#111,font-size:40px;\n"
        "classDef access stroke-width:1.5px,stroke:#7f7f7f,fill:#f6f6f6,color:#111,font-size:40px;\n"
        "classDef wan    stroke-width:2px,stroke:#9467bd,fill:#f2e9fb,color:#111,font-size:40px;\n"
        "classDef dmz    stroke-width:2px,stroke:#d62728,fill:#fdeaea,color:#111,font-size:40px;\n"
        "classDef mgmt   stroke-width:1.5px,stroke:#bcbd22,fill:#fbfbe6,color:#111,font-size:40px;\n"
        "classDef wifi  stroke-width:1.5px,stroke:#1f77b4,fill:#eef7ff,color:#111,font-size:40px;\n"
    )

# -----------------------------
# Р РµРЅРґРµСЂ
# -----------------------------

class MermaidWriter:
    def __init__(self, cfg: Config, norm: Normalized, logger: logging.Logger | None = None):
        self.cfg = cfg
        self.norm = norm
        self.log = logger or logging.getLogger("mermaid_writer")

    def _header(self) -> str:
        # РџСЂРѕР»РѕРі вЂ” Р±РµР· СЏРІРЅРѕРіРѕ РІРєР»СЋС‡РµРЅРёСЏ elk. Р•РіРѕ (РїРѕ СЃС‚Р°РЅРґР°СЂС‚Сѓ) РґРѕР±Р°РІР»СЏРµС‚ РІРЅРµС€РЅСЏСЏ СЃСЂРµРґР°/СЌРєСЃРїРѕСЂС‚С‘СЂ РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё.
        fd = self.cfg.render.flow_direction or "LR"
        fs = self.cfg.render.font_size or "18px"
        ns = self.cfg.render.node_spacing or 60
        rs = self.cfg.render.rank_spacing or 60
        dp = self.cfg.render.diagram_padding or 16
        init_cfg = {
            "theme": "base",
            "themeVariables": {"fontSize": fs},
            "flowchart": {
                "htmlLabels": False,
                "curve": "basis",
                "defaultRenderer": "elk",
                "nodeSpacing": ns,
                "rankSpacing": rs,
                "diagramPadding": dp,
            },
            "themeCSS": ".edgeLabel .label{font-size:" + fs + ";}.nodeLabel{font-size:" + fs + ";}.cluster-label span{font-size:" + fs + ";}",
        }
        header = (
            "%% Р”РёР°РіС€Р°РјРјР° Mermaid NetDocs\n"
            "%% Р РµР¶РёРјС‹: LR + (optional) elk\n"
            + "%%" + "{init: " + json.dumps(init_cfg).replace(" ", " ") + "}" + "%%\n"
            + f"flowchart {fd}\n"
            + "\n"
        )
        return header

    def _group_by_site(self) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
        buckets: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for item in sorted(self.norm.nodes.items(), key=stable_node_key):
            hn, n = item
            site = str(n.get("site") or "UNSPEC")
            buckets.setdefault(site, []).append(item)
        return buckets

    def _render_nodes_plain(self) -> List[str]:
        lines: List[str] = []
        for hn, n in sorted(self.norm.nodes.items(), key=stable_node_key):
            node_id = hn
            lines.append(build_node_line(node_id, n, self.cfg))
        return lines

    def _render_nodes_with_subgraphs(self) -> List[str]:
        lines: List[str] = []
        # Precompute (site -> items) and build nodes
        site_groups = list(self._group_by_site().items())
        for site, items in site_groups:
            lines.append(f'subgraph "{site}"')
            lines.append('  direction TB')
            # Group inside site by zone (first numeric token in hostname)
            by_zone: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
            unzoned: List[Tuple[str, Dict[str, Any]]] = []
            for hn, n in items:
                z = str(n.get("zone") or "").strip()
                if z:
                    by_zone.setdefault(z, []).append((hn, n))
                else:
                    unzoned.append((hn, n))
            # Print zones
            for z in sorted(by_zone.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
                lines.append(f'  subgraph "{z}"')
                lines.append('    direction TB')
                for hn, n in sorted(by_zone[z], key=stable_node_key):
                    lines.append("    " + build_node_line(hn, n, self.cfg))
                lines.append("  end")
            # Unzoned nodes
            for hn, n in sorted(unzoned, key=stable_node_key):
                lines.append("  " + build_node_line(hn, n, self.cfg))
            lines.append("end")

            # After site block: print zone-local edges
            zone_nodes: Dict[str, set] = {z: {hn for hn, _ in lst} for z, lst in by_zone.items()}
            for z in sorted(zone_nodes.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
                lines.append(f'%% ===== Новые связи: {z} =====')
                znodes = zone_nodes[z]
                for e in self.norm.edges:
                    s = e.get("src"); d = e.get("dst")
                    if not s or not d:
                        continue
                    # Assign edge to zone if src in zone; otherwise if dst in zone and src not in zone
                    if s in znodes or (d in znodes and s not in znodes):
                        ln = build_edge_line(e)
                        if ln:
                            lines.append(ln)
        return lines

    def _render_edges(self) -> List[str]:
        lines: List[str] = []
        # РЎС‚Р°Р±РёР»СЊРЅС‹Р№ РїРѕСЂСЏРґРѕРє СЂС‘Р±РµСЂ: РєР°Рє РІ normalize (СѓР¶Рµ РѕС‚СЃРѕСЂС‚РёСЂРѕРІР°РЅРѕ), РїСЂРѕСЃС‚Рѕ РїРµС‡Р°С‚Р°РµРј
        for e in self.norm.edges:
            ln = build_edge_line(e)
            if ln:
                lines.append(ln)
        return lines

    def render(self) -> str:
        parts: List[str] = [self._header()]

        # РЈР·Р»С‹
        if self.cfg.render.use_subgraphs:
            parts.extend(self._render_nodes_with_subgraphs())
        else:
            parts.extend(self._render_nodes_plain())

        parts.append("")  # РїСѓСЃС‚Р°СЏ СЃС‚СЂРѕРєР°

        # Р С‘Р±СЂР°
                # Рёбра
        if self.cfg.render.use_subgraphs:
            node_site: Dict[str, str] = {hn: str(n.get("site") or "UNSPEC") for hn, n in self.norm.nodes.items()}
            for e in self.norm.edges:
                s = e.get("src"); d = e.get("dst")
                if not s or not d:
                    continue
                if node_site.get(s) != node_site.get(d):
                    ln = build_edge_line(e)
                    if ln:
                        parts.append(ln)
        else:
            parts.extend(self._render_edges())
        parts.append("")  # РїСѓСЃС‚Р°СЏ СЃС‚СЂРѕРєР°

        # classDef вЂ” РѕРґРёРЅ СЂР°Р· РІРЅРёР·Сѓ РґРёР°РіСЂР°РјРјС‹
        parts.append(class_defs())

        return "\n".join(parts)


# -----------------------------
# CLI
# -----------------------------

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("mermaid_writer")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

def _default_paths(root: Path) -> tuple[Path, Path, Path]:
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ (config.json, normalized.json, output.mmd)"""
    cfg = root / "config" / "config.json"
    normalized = root / "data" / "output" / "logs" / "normalized.json"
    out_mmd = root / "data" / "output" / "network.mmd"
    return cfg, normalized, out_mmd

if __name__ == "__main__":
    """
    Р—Р°РїСѓСЃРє:
      python -m src.renderers.mermaid_writer

    РџСЂРµРґРїРѕР»Р°РіР°РµС‚, С‡С‚Рѕ:
      - data/output/logs/normalized.json СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚ (РёР· normalize.py)
      - config/config.json СЃСѓС‰РµСЃС‚РІСѓРµС‚
    """
    log = _setup_logger()
    project_root = Path(__file__).resolve().parents[2]  # .../src/renderers -> РєРѕСЂРµРЅСЊ
    cfg_path, norm_path, out_path = _default_paths(project_root)

    try:
        cfg = Config.load(cfg_path)
        norm = load_normalized(norm_path)
        writer = MermaidWriter(cfg, norm, log)
        text = writer.render()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        log.info("Р“РѕС‚РѕРІРѕ: %s", out_path)
    except Exception as e:
        log.error("Р¤Р°С‚Р°Р»СЊРЅР°СЏ РѕС€РёР±РєР°: %s", e)
        raise



