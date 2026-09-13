"""Inline keyboards for MAX messenger."""

from __future__ import annotations

from config import IMAGE_MODELS, MODELS


def _inline_keyboard(buttons: list[list[dict]]) -> list[dict]:
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def available_image_models() -> dict:
    """MAX bot: only free Pollinations models (Flux, Turbo)."""
    return {k: v for k, v in IMAGE_MODELS.items() if v.provider == "pollinations"}


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


def image_models_keyboard(current_model: str) -> list[dict]:
    rows: list[list[dict]] = []
    for key, model in available_image_models().items():
        mark = "✅ " if key == current_model else ""
        rows.append([{
            "type": "callback",
            "text": f"{mark}{model.name}",
            "payload": f"imagemodel:{key}",
        }])
    rows.append([{"type": "callback", "text": "❌ Отмена", "payload": "cancel:image"}])
    return _inline_keyboard(rows)


def cancel_image_keyboard() -> list[dict]:
    return _inline_keyboard([[{"type": "callback", "text": "❌ Отмена", "payload": "cancel:image"}]])


def main_menu_keyboard() -> list[dict]:
    return _inline_keyboard([
        [
            {"type": "callback", "text": "🤖 Модели чата", "payload": "menu:models"},
            {"type": "callback", "text": "🖼 Модели картинок", "payload": "menu:image_models"},
        ],
        [
            {"type": "callback", "text": "🎨 Создать картинку", "payload": "menu:create_image"},
            {"type": "callback", "text": "🗑 Новый чат", "payload": "menu:clear"},
        ],
    ])
