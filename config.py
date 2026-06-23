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
    disable_thinking: bool = False


MODELS: Dict[str, LLMModel] = {
    "gemini-2.0-flash": LLMModel(
        id="gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash",
        provider="google",
        description="Fast & smart model by Google",
        cost_per_message=1,
    ),
    "llama-3.3-70b": LLMModel(
        id="llama-3.3-70b-versatile",
        name="Llama 3.3 70B",
        provider="groq",
        description="Powerful open model by Meta (ultra-fast)",
        cost_per_message=1,
    ),
    "llama-3.1-8b": LLMModel(
        id="llama-3.1-8b-instant",
        name="Llama 3.1 8B",
        provider="groq",
        description="Lightweight & very fast model",
        cost_per_message=1,
    ),
    "qwen3-32b": LLMModel(
        id="qwen/qwen3-32b",
        name="Qwen3 32B",
        provider="groq",
        description="Powerful model by Alibaba",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "qwen3-27b": LLMModel(
        id="qwen/qwen3.6-27b",
        name="Qwen3.6 27B",
        provider="groq",
        description="New Alibaba model (faster & smarter)",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "llama-4-scout": LLMModel(
        id="meta-llama/llama-4-scout-17b-16e-instruct",
        name="Llama 4 Scout",
        provider="groq",
        description="Latest Meta Llama 4 model",
        cost_per_message=1,
    ),
    "compound": LLMModel(
        id="groq/compound",
        name="Groq Compound",
        provider="groq",
        description="Groq's flagship compound model",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "compound-mini": LLMModel(
        id="groq/compound-mini",
        name="Groq Compound Mini",
        provider="groq",
        description="Fast compact model by Groq",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "gpt-oss-20b": LLMModel(
        id="openai/gpt-oss-20b",
        name="ChatGPT OSS 20B (Free)",
        provider="groq",
        description="OpenAI open model — fast, free via Groq",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "gpt-oss-120b": LLMModel(
        id="openai/gpt-oss-120b",
        name="ChatGPT OSS 120B (Free)",
        provider="groq",
        description="OpenAI flagship open model — free via Groq",
        cost_per_message=1,
        disable_thinking=True,
    ),
    "deepseek-v3": LLMModel(
        id="deepseek-chat",
        name="DeepSeek V3",
        provider="deepseek",
        description="DeepSeek's powerful general-purpose model",
        cost_per_message=1,
    ),
    "deepseek-r1": LLMModel(
        id="deepseek-reasoner",
        name="DeepSeek R1",
        provider="deepseek",
        description="DeepSeek's advanced reasoning model",
        cost_per_message=1,
    ),
}

DEFAULT_MODEL = "llama-3.3-70b"


@dataclass
class ImageModel:
    id: str
    name: str
    provider: str
    description: str
    cost_per_image: int


IMAGE_MODELS: Dict[str, ImageModel] = {
    "gemini-image": ImageModel(
        id="google/gemini-2.5-flash-image",
        name="Gemini Image",
        provider="openrouter",
        description="Google Gemini — high quality",
        cost_per_image=3,
    ),
    "flux-klein": ImageModel(
        id="black-forest-labs/flux.2-klein-4b",
        name="Flux Klein",
        provider="openrouter",
        description="Fast Flux model by Black Forest Labs",
        cost_per_image=3,
    ),
    "flux-free": ImageModel(
        id="flux",
        name="Flux (Free)",
        provider="pollinations",
        description="Free generation, good quality",
        cost_per_image=0,
    ),
    "turbo-free": ImageModel(
        id="turbo",
        name="Turbo (Free)",
        provider="pollinations",
        description="Free and very fast",
        cost_per_image=0,
    ),
}

DEFAULT_IMAGE_MODEL = "flux-free"
IMAGE_MAX_TOKENS = 1024
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024

# Subscription
SUBSCRIPTION_PRICE_STARS = 299   # price in Telegram Stars
SUBSCRIPTION_DAYS = 30           # duration in days
PREMIUM_BOT_USERNAME = "PremiumBot"
# Opens PremiumBot stars purchase UI inline (no chat switch).
PREMIUM_BOT_STARS_URL = f"https://t.me/{PREMIUM_BOT_USERNAME}?start=stars"
# Opens native stars top-up sheet with required balance hint.
STARS_TOPUP_URL = f"tg://stars_topup?balance={SUBSCRIPTION_PRICE_STARS}"

# Flood protection
RATE_LIMIT_MESSAGES = 5     # max messages
RATE_LIMIT_WINDOW = 60      # per N seconds

# Free requests
FREE_CREDITS_ON_START = 5       # on registration
DAILY_FREE_CREDITS = 2          # every day
REFERRAL_BONUS_CREDITS = 3      # per referral

# Dialog context
MAX_CONTEXT_MESSAGES = 20
MAX_CONTEXT_CHARS = 4000

# Config from .env
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_PROBE_INTERVAL: int = int(os.getenv("OPENROUTER_PROBE_INTERVAL", "1800"))
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DATABASE_URL: str = "sqlite+aiosqlite:///bot.db"
