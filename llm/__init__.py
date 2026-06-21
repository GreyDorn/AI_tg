from config import MODELS
from llm.base import BaseLLM
from llm.gemini import GeminiLLM
from llm.groq_llm import GroqLLM
from llm.openrouter import OpenRouterLLM
from llm.deepseek import DeepSeekLLM

_providers: dict[str, BaseLLM] = {
    "google": GeminiLLM(),
    "groq": GroqLLM(),
    "openrouter": OpenRouterLLM(),
    "deepseek": DeepSeekLLM(),
}


def get_llm(model_key: str) -> tuple[BaseLLM, str, bool]:
    model = MODELS[model_key]
    llm = _providers[model.provider]
    return llm, model.id, model.disable_thinking
