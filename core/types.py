from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

from db.models import Message


class CreditStatus(Enum):
    OK = "ok"
    DENIED = "denied"


class LlmErrorKind(Enum):
    RATE_LIMITED = "rate_limited"
    PROVIDER_LIMIT = "provider_limit"
    MODEL_GONE = "model_gone"
    CONTEXT_TOO_LARGE = "context_too_large"
    VISION_UNAVAILABLE = "vision_unavailable"
    VISION_FAILED = "vision_failed"
    EMPTY_RESPONSE = "empty_response"
    GENERIC = "generic"


@dataclass
class CreditCheck:
    status: CreditStatus
    credits_spent: int = 0


@dataclass
class TextChatSetup:
    conv_id: int
    model_key: str
    model_name: str
    credits_spent: int
    context: list[Message]


@dataclass
class VisionChatSetup:
    conv_id: int
    vision_key: str
    vision_name: str
    credits_spent: int
    auto_switched: bool
    revert_model_key: str | None
    image_bytes: bytes
    mime_type: str
    prompt: str
    context: list[Message]


@dataclass
class ImageGenerationResult:
    image_bytes: bytes
    mime_type: str
    model_key: str
    model_name: str
    credits_spent: int


# Type alias for LLM token streams consumed by messengers.
ChatStream = AsyncIterator[str]
