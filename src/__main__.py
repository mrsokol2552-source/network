# -*- coding: utf-8 -*-
"""
Единая точка входа конвейера Mermaid NetDocs:
  1) Загружает config.json и inventory.json
  2) (опц.) Прогоняет TextFSM-парсинг CLI
  3) Нормализует данные
  4) Рендерит Mermaid .mmd

Запуск:
  python -m src --run all
  python -m src --run normalize,render
  python -m src --run render --config config/config.json --normalized data/output/logs/normalized.json

Пути по умолчанию берутся из config/config.json.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List

# Локальные модули
from src.parsers.textfsm_loader import Config as LoaderConfig, Inventory as LoaderInventory, TextFSMParser
from src.parsers.normalize import Inventory as NormInventory, Normalizer
from src.renderers.mermaid_writer import Config as RenderConfig, MermaidWriter, load_normalized

# -----------------------------
# Логирование
# -----------------------------

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("netdocs")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger

# -----------------------------
# Утилиты
# -----------------------------

def project_root_from_here() -> Path:
    """Определяем корень как два уровня выше этого файла: .../src/__main__.py -> корень."""
    return Path(__file__).resolve().parents[1]

def default_paths(root: Path):
    cfg = root / "config" / "config.json"
    inv = root / "data" / "input" / "inventory.json"
    logs_dir = root / "data" / "output" / "logs"
    parsed_textfsm = logs_dir / "parsed_textfsm.json"
    normalized = logs_dir / "normalized.json"
    out_mmd = root / "data" / "output" / "network.mmd"
    return cfg, inv, logs_dir, parsed_textfsm, normalized, out_mmd

# -----------------------------
# Шаги конвейера
# -----------------------------

def step_textfsm(cfg_path: Path, inv_path: Path, parsed_out: Path, log: logging.Logger):
    log.info("Шаг: TextFSM-парсинг CLI")
    cfg = LoaderConfig.load(cfg_path)
    inv = LoaderInventory.load(inv_path)
    parser = TextFSMParser(cfg, inv, log)
    data = parser.parse_all()

    parsed_out.parent.mkdir(parents=True, exist_ok=True)
    parsed_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Готово: %s", parsed_out)

def step_normalize(inv_path: Path, normalized_out: Path, log: logging.Logger):
    log.info("Шаг: Нормализация")
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
    normalized_out.parent.mkdir(parents=True, exist_ok=True)
    normalized_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Готово: %s (nodes=%d, edges=%d, warnings=%d)",
             normalized_out, len(norm.nodes), len(norm.edges), len(norm.warnings))

def step_render(cfg_path: Path, normalized_path: Path, out_mmd: Path, log: logging.Logger):
    log.info("Шаг: Рендер Mermaid")
    rcfg = RenderConfig.load(cfg_path)
    norm = load_normalized(normalized_path)
    writer = MermaidWriter(rcfg, norm, log)
    text = writer.render()

    out_mmd.parent.mkdir(parents=True, exist_ok=True)
    out_mmd.write_text(text, encoding="utf-8")
    log.info("Готово: %s", out_mmd)

# -----------------------------
# main
# -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mermaid NetDocs — конвейер генерации .mmd")
    p.add_argument("--run", default="all",
                   help="Какие шаги выполнить: all | textfsm | normalize | render | список через запятую")
    p.add_argument("--config", type=Path, help="Путь к config.json")
    p.add_argument("--inventory", type=Path, help="Путь к inventory.json")
    p.add_argument("--normalized", type=Path, help="Путь к normalized.json (для шага render)")
    p.add_argument("--out", type=Path, help="Путь для network.mmd (для шага render)")
    p.add_argument("--log-level", default="INFO", help="Уровень логирования (DEBUG/INFO/...)")
    return p.parse_args()

def main():
    args = parse_args()
    log = setup_logger(args.log_level)

    root = project_root_from_here()
    cfg_def, inv_def, logs_dir, parsed_def, normalized_def, out_mmd_def = default_paths(root)

    cfg_path = args.config or cfg_def
    inv_path = args.inventory or inv_def
    normalized_path = args.normalized or normalized_def
    out_mmd_path = args.out or out_mmd_def

    steps: List[str] = [s.strip().lower() for s in (args.run or "all").split(",")]
    if "all" in steps:
        steps = ["textfsm", "normalize", "render"]

    log.debug("config=%s, inventory=%s", cfg_path, inv_path)
    log.debug("normalized=%s, out=%s", normalized_path, out_mmd_path)
    log.debug("steps=%s", steps)

    try:
        if "textfsm" in steps:
            step_textfsm(cfg_path, inv_path, parsed_def, log)
        if "normalize" in steps:
            step_normalize(inv_path, normalized_path, log)
        if "render" in steps:
            # убеждаемся, что normalized существует (если запускали только render)
            if not normalized_path.exists():
                log.error("Файл нормализации не найден: %s. Сначала выполните шаг normalize.", normalized_path)
                raise SystemExit(2)
            step_render(cfg_path, normalized_path, out_mmd_path, log)

        log.info("Pipeline OK")
    except SystemExit:
        raise
    except Exception as e:
        log.error("Фатальная ошибка конвейера: %s", e)
        raise

if __name__ == "__main__":
    main()