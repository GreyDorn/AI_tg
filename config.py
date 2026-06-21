from dataclasses import dataclass, field
from typing import Dict
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class LLMModel:
    id: str
    name: str
    provider: str
    description: str
    cost_per_message: int
    disable_thinking: bool = False  # отключить режим рассуждений (для Qwen3 и др.)


MODELS: Dict[str, LLMModel] = {
    "gemini-2.0-flash": LLMModel(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="google",
        description="Быстрая и умная модель от Google",
        cost_per_message=1,
    ),
    "llama-3.3-70b": LLMModel(
        id="llama-3.3-70b-versatile",
        name="Llama 3.3 70B",
        provider="groq",
        description="Мощная открытая модель Meta (сверхбыстро)",
        cost_per_message=1,
    ),
    "llama-3.1-8b": LLMModel(
        id="llama-3.1-8b-instant",
        name="Llama 3.1 8B",
        provider="groq",
        description="Лёгкая и очень быстрая модель",
        cost_per_message=1,
    ),
    "qwen3-32b": LLMModel(
        id="qwen/qwen3-32b",
        name="Qwen3 32B",
        provider="groq",
        description="Мощная модель Alibaba от Alibaba",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "qwen3-27b": LLMModel(
        id="qwen/qwen3.6-27b",
        name="Qwen3.6 27B",
        provider="groq",
        description="Новая модель Alibaba (быстрее и умнее)",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "llama-4-scout": LLMModel(
        id="meta-llama/llama-4-scout-17b-16e-instruct",
        name="Llama 4 Scout",
        provider="groq",
        description="Новейшая модель Meta Llama 4",
        cost_per_message=1,
    ),
    "compound": LLMModel(
        id="groq/compound",
        name="Groq Compound",
        provider="groq",
        description="Флагманская модель от Groq",
        cost_per_message=1,
    ),
    "compound-mini": LLMModel(
        id="groq/compound-mini",
        name="Groq Compound Mini",
        provider="groq",
        description="Быстрая модель Groq",
        cost_per_message=1,
    ),
}

DEFAULT_MODEL = "llama-3.3-70b"

# Пакеты покупки кредитов за Telegram Stars
# ключ — id пакета, значение — (stars, credits, label)
CREDIT_PACKAGES = {
    "pack_15":  (15,  15,  "15 ⭐ → 15 🔥"),
    "pack_50":  (50,  60,  "50 ⭐ → 60 🔥 (+20%)"),
    "pack_100": (100, 130, "100 ⭐ → 130 🔥 (+30%)"),
    "pack_300": (300, 420, "300 ⭐ → 420 🔥 (+40%)"),
}

# Защита от флуда
RATE_LIMIT_MESSAGES = 5     # макс. сообщений
RATE_LIMIT_WINDOW = 60      # за N секунд

# Кредиты
FREE_CREDITS_ON_START = 5       # при регистрации
DAILY_FREE_CREDITS = 2          # каждый день
REFERRAL_BONUS_CREDITS = 3      # за каждого реферала

# Контекст диалога
MAX_CONTEXT_MESSAGES = 20       # макс. сообщений в контексте
MAX_CONTEXT_CHARS = 4000        # макс. символов в контексте

# Конфиг из .env
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
DATABASE_URL: str = "sqlite+aiosqlite:///bot.db"
