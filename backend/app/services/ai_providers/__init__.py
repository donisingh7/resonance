from app.core.config import settings
from app.services.ai_providers.base import AIProvider
from app.services.ai_providers.mock_provider import MockAIProvider
from app.services.ai_providers.openai_provider import OpenAIProvider

_PROVIDERS: dict[str, type[AIProvider]] = {
    "mock": MockAIProvider,
    "openai": OpenAIProvider,
}


def get_ai_provider(name: str | None = None) -> AIProvider:
    provider_name = (name or settings.ai_provider).strip().lower()

    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AI provider '{provider_name}'. Available: {', '.join(_PROVIDERS)}."
        )

    return provider_cls()
