"""Подготовка истории диалога для LLM: system prompt и умная обрезка."""
from config import CHAT_SYSTEM_PROMPT, MAX_CONTEXT_CHARS
from db.models import Message


def messages_to_history(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _history_size(history: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in history)


def smart_trim_history(
    history: list[dict],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict]:
    """Обрезает историю, сохраняя system prompt и первое сообщение пользователя."""
    if not history or _history_size(history) <= max_chars:
        return history

    system: list[dict] = []
    body = history
    if body[0].get("role") == "system":
        system = [body[0]]
        body = body[1:]

    budget = max_chars - _history_size(system)
    if budget <= 0 or not body:
        return system

    first_user = next((m for m in body if m["role"] == "user"), None)
    selected = list(body)

    while selected and _history_size(system) + _history_size(selected) > max_chars:
        removed = False
        for i, msg in enumerate(selected):
            if first_user and msg is first_user:
                continue
            selected.pop(i)
            removed = True
            break
        if not removed:
            break

    if first_user and first_user not in selected:
        selected = [first_user, *selected]
        while len(selected) > 1 and _history_size(system) + _history_size(selected) > max_chars:
            if selected[1] is first_user:
                selected.pop(2) if len(selected) > 2 else selected.pop(1)
            else:
                selected.pop(1)

    return system + selected


def prepare_chat_history(
    messages: list[Message],
    *,
    system_prompt: str | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict]:
    """Конвертирует сообщения БД в историю API с system prompt и умной обрезкой."""
    history = messages_to_history(messages)
    prompt = system_prompt if system_prompt is not None else CHAT_SYSTEM_PROMPT

    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": prompt})
    else:
        history[0] = {"role": "system", "content": prompt}

    return smart_trim_history(history, max_chars)
