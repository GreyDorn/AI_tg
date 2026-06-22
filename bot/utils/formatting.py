import html
import re

_PLACEHOLDER = "\x00"


def format_model_text(text: str) -> str:
    """Convert common Markdown from LLMs to Telegram HTML."""
    if not text:
        return text

    protected: list[str] = []

    def _protect(pattern: str, content: str, flags: int = 0) -> str:
        def repl(match: re.Match[str]) -> str:
            protected.append(match.group(1))
            return f"{_PLACEHOLDER}{len(protected) - 1}{_PLACEHOLDER}"

        return re.sub(pattern, repl, content, flags=flags)

    text = _protect(r"```(?:[\w-]+\n)?(.*?)```", text, flags=re.DOTALL)
    text = _protect(r"`([^`\n]+)`", text)
    text = html.escape(text, quote=False)

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<b>\1</b>", text)
    text = re.sub(r"(?<![_a-zA-Z0-9])_([^_\n]+)_(?![_a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )

    for index, item in enumerate(protected):
        escaped = html.escape(item, quote=False)
        if "\n" in item:
            replacement = f"<pre><code>{escaped}</code></pre>"
        else:
            replacement = f"<code>{escaped}</code>"
        text = text.replace(f"{_PLACEHOLDER}{index}{_PLACEHOLDER}", replacement, 1)

    return text
