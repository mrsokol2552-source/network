# -*- coding: utf-8 -*-
"""
mermaid_writer.py — генерация Mermaid (.mmd) из нормализованного графа.

Вход:
- config/config.json (render.*, paths.*)
- data/output/logs/normalized.json (из normalize.py)

Выход:
- data/output/network.mmd

Подчиняется правилам из standards/mermaid_style.md:
- flowchart LR, elk renderer (если включён в среде — добавляется отдельно)
- классы core/dist/access/wan/dmz/mgmt
- стабильный порядок узлов/рёбер
- опциональные subgraph (по site/role в простом варианте — по site)

Примечание: htmlLabels=false, поэтому перенос строки — '\\n' в лейблах.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Tuple

# YAML больше не используется; конфиг читаем как JSON


# -----------------------------
# Конфиг DTO
# -----------------------------

@dataclass
class RenderConfig:
    layout_engine: str            # "elk" | "dagre" (мы печатаем пролог одинаково)
    flow_direction: str           # "LR" | "TD"
    use_subgraphs: bool
    label_verbosity: str          # "none" | "brief" | "full"
    show_ports: bool
    show_vlans: bool
    show_ips: bool


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
        root = path.parent.parent  # .../config -> корень
        r = raw.get("render", {})
        render = RenderConfig(
            layout_engine=r.get("layout_engine", "elk"),
            flow_direction=r.get("flow_direction", "LR"),
            use_subgraphs=bool(r.get("use_subgraphs", False)),
            label_verbosity=r.get("label_verbosity", "full"),
            show_ports=bool(r.get("show_ports", True)),
            show_vlans=bool(r.get("show_vlans", True)),
            show_ips=bool(r.get("show_ips", True)),
        )
        p = raw.get("paths", {})
        paths = PathsConfig(
            output_mermaid=(root / p.get("output_mermaid", "data/output/network.mmd")).resolve(),
            standards_file=(root / p.get("standards_file", "standards/mermaid_style.md")).resolve(),
        )
        return Config(render=render, paths=paths, root=root)


# -----------------------------
# Нормализованные данные
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
# Вспомогательные
# -----------------------------

ROLE_ORDER = ["core", "dist", "access", "wan", "dmz", "mgmt"]

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
    """Простой экранировщик для Mermaid label (без htmlLabels)."""
    if text is None:
        return ""
    # Mermaid нормально переносит \n, экранируем только кавычки
    return str(text).replace('"', '\\"')

def build_node_line(node_id: str, n: Dict[str, Any], cfg: Config) -> str:
    """
    Нода печатается как:
    ID["DEN-CORE-10-20-03\n10.10.0.1\nC9200"]:::core
    """
    primary = n.get("labels", {}).get("primary") or n.get("hostname") or node_id
    extras: List[str] = n.get("labels", {}).get("extra") or []
    # В зависимости от verbosity можно убрать extras
    extra_text = ""
    if cfg.render.label_verbosity == "full" and extras:
        extra_text = "<br/>" + "<br/>".join(extras[:5])

    pp = primary.replace("\\n", "<br/>").replace("\n", "<br/>")
    label = esc(pp) + extra_text
    cls = (n.get("class") or "access").lower()
    return f'{node_id}["{label}"]:::{cls}'

def build_edge_line(e: Dict[str, Any]) -> str:
    """
    A -- "Gi1/0/1 | 1G | Uplink to ACCESS" --- B
    Если нет dst — рисуем висячее ребро к анонимной точке? В Mermaid так лучше не делать.
    В нашем конвейере такие рёбра всё равно будут, но Mermaid требует валидного dst.
    Поэтому пропускаем рёбра без dst.
    """
    src = e.get("src")
    dst = e.get("dst")
    if not src or not dst:
        return ""  # пропустим
    label = e.get("label")
    if label:
        return f'{src} -- "{esc(label)}" --- {dst}'
    return f"{src} --- {dst}"

def class_defs() -> str:
    return (
        "classDef core   stroke-width:2px,stroke:#1f77b4,fill:#e6f1fb,color:#111;\n"
        "classDef dist   stroke-width:2px,stroke:#2ca02c,fill:#eaf7ea,color:#111;\n"
        "classDef access stroke-width:1.5px,stroke:#7f7f7f,fill:#f6f6f6,color:#111;\n"
        "classDef wan    stroke-width:2px,stroke:#9467bd,fill:#f2e9fb,color:#111;\n"
        "classDef dmz    stroke-width:2px,stroke:#d62728,fill:#fdeaea,color:#111;\n"
        "classDef mgmt   stroke-width:1.5px,stroke:#bcbd22,fill:#fbfbe6,color:#111;\n"
        "classDef wifi  stroke-width:1.5px,stroke:#1f77b4,fill:#eef7ff,color:#111;\n"
    )

# -----------------------------
# Рендер
# -----------------------------

class MermaidWriter:
    def __init__(self, cfg: Config, norm: Normalized, logger: logging.Logger | None = None):
        self.cfg = cfg
        self.norm = norm
        self.log = logger or logging.getLogger("mermaid_writer")

    def _header(self) -> str:
        # Пролог — без явного включения elk. Его (по стандарту) добавляет внешняя среда/экспортёр при необходимости.
        fd = self.cfg.render.flow_direction or "LR"
        header = (
            "%% Диаграмма генерирована Mermaid NetDocs\n"
            "%% Режимы: LR + (optional) elk\n"
            "%%{init: {\"theme\": \"base\", \"flowchart\": {\"htmlLabels\": true, \"curve\": \"basis\"}}}%%\n"
            f"flowchart {fd}\n"
            "\n"
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
        for site, items in self._group_by_site().items():
            lines.append(f'subgraph "{site}"')
            # Внутри сайта дополнительная группировка по роли (плоско, без вложений глубже 2)
            by_role: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
            for hn, n in items:
                by_role.setdefault(str(n.get("role") or "access").lower(), []).append((hn, n))
            for role in ROLE_ORDER:
                if role not in by_role:
                    continue
                lines.append(f'  subgraph "{role}"')
                for hn, n in by_role[role]:
                    lines.append("    " + build_node_line(hn, n, self.cfg))
                lines.append("  end")
            lines.append("end")
        return lines

    def _render_edges(self) -> List[str]:
        lines: List[str] = []
        # Стабильный порядок рёбер: как в normalize (уже отсортировано), просто печатаем
        for e in self.norm.edges:
            ln = build_edge_line(e)
            if ln:
                lines.append(ln)
        return lines

    def render(self) -> str:
        parts: List[str] = [self._header()]

        # Узлы
        if self.cfg.render.use_subgraphs:
            parts.extend(self._render_nodes_with_subgraphs())
        else:
            parts.extend(self._render_nodes_plain())

        parts.append("")  # пустая строка

        # Рёбра
        parts.extend(self._render_edges())

        parts.append("")  # пустая строка

        # classDef — один раз внизу диаграммы
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
    """Возвращает (config.json, normalized.json, output.mmd)"""
    cfg = root / "config" / "config.json"
    normalized = root / "data" / "output" / "logs" / "normalized.json"
    out_mmd = root / "data" / "output" / "network.mmd"
    return cfg, normalized, out_mmd

if __name__ == "__main__":
    """
    Запуск:
      python -m src.renderers.mermaid_writer

    Предполагает, что:
      - data/output/logs/normalized.json уже существует (из normalize.py)
      - config/config.json существует
    """
    log = _setup_logger()
    project_root = Path(__file__).resolve().parents[2]  # .../src/renderers -> корень
    cfg_path, norm_path, out_path = _default_paths(project_root)

    try:
        cfg = Config.load(cfg_path)
        norm = load_normalized(norm_path)
        writer = MermaidWriter(cfg, norm, log)
        text = writer.render()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        log.info("Готово: %s", out_path)
    except Exception as e:
        log.error("Фатальная ошибка: %s", e)
        raise