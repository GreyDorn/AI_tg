"""Inline keyboards for MAX messenger."""

from __future__ import annotations

from config import MODELS


def _inline_keyboard(buttons: list[list[dict]]) -> list[dict]:
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def models_keyboard(current_model: str) -> list[dict]:
    rows: list[list[dict]] = []
    row: list[dict] = []
    for key, model in MODELS.items():
        mark = "✅ " if key == current_model else ""
        vision = " 📷" if model.supports_vision else ""
        row.append({
            "type": "callback",
            "text": f"{mark}{model.name}{vision}",
            "payload": f"model:{key}",
        })
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return _inline_keyboard(rows)


def main_menu_keyboard() -> list[dict]:
    return _inline_keyboard([
        [
            {"type": "callback", "text": "🤖 Модели", "payload": "menu:models"},
            {"type": "callback", "text": "🗑 Новый чат", "payload": "menu:clear"},
        ],
    ])
