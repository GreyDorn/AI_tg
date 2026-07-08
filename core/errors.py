from llm.gemini import VISION_UNAVAILABLE_MSG
from core.types import LlmErrorKind


def classify_llm_error(error: Exception | str, *, vision_mode: bool = False) -> LlmErrorKind:
    error_str = str(error)
    low = error_str.lower()

    if vision_mode:
        if VISION_UNAVAILABLE_MSG in error_str or "gemini api" in low:
            return LlmErrorKind.VISION_UNAVAILABLE
        return LlmErrorKind.VISION_FAILED

    if "429" in error_str or "quota" in low or "rate" in low or "resource_exhausted" in low:
        return LlmErrorKind.RATE_LIMITED
    if "402" in error_str or "insufficient balance" in low or "payment required" in low:
        return LlmErrorKind.PROVIDER_LIMIT
    if "decommissioned" in low or "not supported" in low:
        return LlmErrorKind.MODEL_GONE
    if "too large" in low or "entity too large" in low or "context" in low:
        return LlmErrorKind.CONTEXT_TOO_LARGE
    return LlmErrorKind.GENERIC
