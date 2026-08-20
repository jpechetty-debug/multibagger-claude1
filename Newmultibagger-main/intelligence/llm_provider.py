from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.observability.logger import get_logger

_log = get_logger("intelligence.llm_provider")

class LLMProvider(ABC):
    """
    Abstract base class for all LLM interactions.
    This keeps the Sovereign Terminal model-agnostic.
    """
    
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        Generate a response given a system and user prompt.
        """
        pass


class MockProvider(LLMProvider):
    """
    A mock provider for Phase 1 or testing environments where an LLM is not available.
    """
    
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        _log.info("MockProvider: generate called")
        return f"[MOCK GENERATED TEXT]\nSystem Prompt: {system_prompt[:50]}...\nUser Prompt: {user_prompt[:50]}..."


# Later, these can be implemented as needed:
# class OpenAIProvider(LLMProvider): ...
# class AnthropicProvider(LLMProvider): ...
# class LocalProvider(LLMProvider): ...
# class MCPProvider(LLMProvider): ...

def get_llm_provider(provider_type: str = "mock") -> LLMProvider:
    if provider_type == "mock":
        return MockProvider()
    # Add other provider initializations here based on config or type
    raise ValueError(f"Unknown provider type: {provider_type}")
