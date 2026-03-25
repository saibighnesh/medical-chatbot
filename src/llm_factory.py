"""
LLM Factory - Dynamic LLM Provider Loading
Supports Gemini, OpenAI, and Claude with unified interface
"""

import os

from src.database import get_active_provider, get_api_key, set_active_provider


class LLMFactory:
    """Factory for creating and managing LLM instances"""

    def __init__(self):
        self.current_llm = None
        self.current_provider = None

    def get_llm(self, provider=None, api_key=None, **kwargs):
        """
        Get an LLM instance

        Args:
            provider: Provider name (gemini, openai, claude). If None, uses active provider.
            api_key: API key. If None, retrieves from database.
            **kwargs: Additional parameters for the LLM

        Returns:
            LLM instance
        """
        # If no provider specified, get active one
        if not provider:
            active = get_active_provider()
            if active:
                provider = active["provider"]
                api_key = active["api_key"]
            else:
                # Fallback to environment variable
                if os.getenv("GOOGLE_API_KEY"):
                    provider = "gemini"
                    api_key = os.getenv("GOOGLE_API_KEY")
                else:
                    raise ValueError("No active LLM provider configured")

        # If no API key provided, get from database
        if not api_key:
            api_key = get_api_key(provider)
            if not api_key:
                raise ValueError(f"No API key found for provider: {provider}")

        # Create LLM instance based on provider
        if provider == "gemini":
            return self._create_gemini_llm(api_key, **kwargs)
        elif provider == "openai":
            return self._create_openai_llm(api_key, **kwargs)
        elif provider == "claude":
            return self._create_claude_llm(api_key, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _create_gemini_llm(self, api_key, **kwargs):
        """Create Google Gemini LLM instance"""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            default_params = {
                "model": "gemini-2.0-flash-exp",
                "google_api_key": api_key,
                "temperature": 0.7,
                "max_output_tokens": 1024,
            }
            default_params.update(kwargs)

            self.current_llm = ChatGoogleGenerativeAI(**default_params)
            self.current_provider = "gemini"
            return self.current_llm

        except ImportError:
            raise ImportError("langchain-google-genai not installed. Run: pip install langchain-google-genai")

    def _create_openai_llm(self, api_key, **kwargs):
        """Create OpenAI LLM instance"""
        try:
            from langchain_openai import ChatOpenAI

            default_params = {"model": "gpt-4", "openai_api_key": api_key, "temperature": 0.7, "max_tokens": 1024}
            default_params.update(kwargs)

            self.current_llm = ChatOpenAI(**default_params)
            self.current_provider = "openai"
            return self.current_llm

        except ImportError:
            raise ImportError("langchain-openai not installed. Run: pip install langchain-openai")

    def _create_claude_llm(self, api_key, **kwargs):
        """Create Anthropic Claude LLM instance"""
        try:
            from langchain_anthropic import ChatAnthropic

            default_params = {
                "model": "claude-3-5-sonnet-20241022",
                "anthropic_api_key": api_key,
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            default_params.update(kwargs)

            self.current_llm = ChatAnthropic(**default_params)
            self.current_provider = "claude"
            return self.current_llm

        except ImportError:
            raise ImportError("langchain-anthropic not installed. Run: pip install langchain-anthropic")

    def switch_provider(self, provider):
        """
        Switch to a different LLM provider

        Args:
            provider: Provider name to switch to

        Returns:
            New LLM instance
        """
        # Set as active in database
        set_active_provider(provider)

        # Create new LLM
        return self.get_llm(provider=provider)

    def validate_api_key(self, provider, api_key):
        """
        Validate an API key by making a test request

        Args:
            provider: Provider name
            api_key: API key to test

        Returns:
            dict with 'valid' (bool) and 'message' (str)
        """
        try:
            # Each provider uses a different kwarg name for token limits
            token_kwargs = {
                "gemini": {"max_output_tokens": 50},
                "openai": {"max_tokens": 50},
                "claude": {"max_tokens": 50},
            }
            llm = self.get_llm(provider=provider, api_key=api_key, **token_kwargs.get(provider, {}))

            # Make a test request
            test_prompt = "Say 'OK' if you can read this."
            response = llm.invoke(test_prompt)

            return {
                "valid": True,
                "message": f"{provider.capitalize()} API key is valid",
                "response": str(response.content)[:100],
            }

        except Exception as e:
            return {"valid": False, "message": f"API key validation failed: {str(e)}"}

    def get_current_provider(self):
        """Get currently loaded provider name"""
        return self.current_provider


# Global factory instance
_llm_factory = None


def get_llm_factory():
    """Get global LLM factory instance"""
    global _llm_factory
    if _llm_factory is None:
        _llm_factory = LLMFactory()
    return _llm_factory


# Convenience functions
def get_active_llm(**kwargs):
    """Get the currently active LLM instance"""
    return get_llm_factory().get_llm(**kwargs)


def switch_llm_provider(provider):
    """Switch to a different LLM provider"""
    return get_llm_factory().switch_provider(provider)


def validate_api_key(provider, api_key):
    """Validate an API key"""
    return get_llm_factory().validate_api_key(provider, api_key)
