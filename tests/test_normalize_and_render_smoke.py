# -*- coding: utf-8 -*-
"""
Smoke-тест нормализации и рендера без запуска всего конвейера.
Запуск:
  pytest -q
"""

from pathlib import Path
import json

from src.parsers.normalize import Inventory as NormInventory, Normalizer
from src.renderers.mermaid_writer import Config as RenderConfig, MermaidWriter


def project_root() -> Path:
    # tests/ -> корень проекта
    return Path(__file__).resolve().parents[1]


def test_normalize_smoke():
    root = project_root()
    inv_path = root / "data" / "input" / "inventory.json"
    assert inv_path.exists(), "inventory.json отсутствует — создай по шагу 5"

    inv = NormInventory.load(inv_path)
    norm = Normalizer(inv).run()

    # Минимальные проверки
    assert len(norm.nodes) >= 1, "Ожидали хотя бы 1 узел"
    # Все подписи рёбер укладываются в 80 символов (см. normalize.truncate)
    for e in norm.edges:
        label = e.get("label") or ""
        assert len(label) <= 80, f"Слишком длинная подпись ребра (>80): {label!r}"

    # Сериализация не падает
    payload = {
        "nodes": norm.nodes,
        "edges": norm.edges,
        "meta": {"warnings": norm.warnings, "stats": {"nodes": len(norm.nodes), "edges": len(norm.edges)}},
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert text and text.startswith("{"), "Должны получить JSON-текст"


def test_render_smoke(tmp_path: Path):
    root = project_root()
    cfg_path = root / "config" / "config.json"
    assert cfg_path.exists(), "config.json отсутствует — создай по шагу 2"

    # Подготовим нормализованные данные прямо тут
    inv_path = root / "data" / "input" / "inventory.yml"
    inv = NormInventory.load(inv_path)
    norm = Normalizer(inv).run()

    # Загружаем конфиг рендера
    rcfg = RenderConfig.load(cfg_path)

    # Генерируем текст .mmd
    text = MermaidWriter(rcfg, norm).render()

    # Проверки: заголовок, flowchart, classDef присутствуют
    assert "flowchart " in text, "В прологе должен быть flowchart"
    assert "classDef core" in text and "classDef access" in text, "Должны быть определения классов"
    # В узлах должны встречаться hostnames из inventory
    for hn in norm.nodes.keys():
        assert hn in text, f"В выводе Mermaid не найден узел {hn}"

    # Временная запись в файл — как пример
    out_file = tmp_path / "network_test.mmd"
    out_file.write_text(text, encoding="utf-8")
    assert out_file.exists() and out_file.stat().st_size > 0