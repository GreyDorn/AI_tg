from config import MODELS
from llm.base import BaseLLM
from llm.gemini import GeminiLLM
from llm.groq_llm import GroqLLM
from llm.openrouter import OpenRouterLLM

_providers: dict[str, BaseLLM] = {
    "google": GeminiLLM(),
    "groq": GroqLLM(),
    "openrouter": OpenRouterLLM(),
}


def get_llm(model_key: str) -> tuple[BaseLLM, str, bool]:
    """Возвращает (llm_instance, model_id, disable_thinking) по ключу из MODELS."""
    model = MODELS[model_key]
    llm = _providers[model.provider]
    return llm, model.id, model.disable_thinking
