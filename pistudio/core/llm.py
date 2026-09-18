"""Optional LLM payload generation.

Everything else in the studio works offline.  This module is only reached
when generating payloads or conversation scripts with a model, which needs::

    pip install prompt-injection-studio[llm]

Provider selection is by environment variable so there is no config file to
manage:

- ``PISTUDIO_LLM_PROVIDER`` — ``openai``, ``anthropic``, ``google``, ``groq``,
  ``ollama``, ``lm_studio`` or ``local``
- ``PISTUDIO_LLM_MODEL`` — model name (optional; a sensible default is used)
- ``PISTUDIO_LLM_BASE_URL`` — required for local providers
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator

__all__ = [
    "LLM_INSTALL_HINT",
    "create_agent_model",
    "resolve_model",
    "with_api_key",
]

LLM_INSTALL_HINT = "pip install prompt-injection-studio[llm]"

_ENV_VAR = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
}

_LOCAL_PROVIDERS = frozenset({"ollama", "lm_studio", "local"})

_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "google": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
}


def resolve_model() -> tuple[str, str, str] | None:
    """Resolve the configured provider from the environment.

    Returns:
        ``(provider, api_key, base_url)``, or ``None`` when no provider is
        configured or its API key is missing.  Callers treat ``None`` as
        "LLM generation unavailable" and fall back to built-in payloads.
    """
    provider = os.environ.get("PISTUDIO_LLM_PROVIDER", "").strip().lower()
    if not provider:
        return None

    base_url = os.environ.get("PISTUDIO_LLM_BASE_URL", "").strip()
    if provider in _LOCAL_PROVIDERS:
        return provider, "", base_url or "http://localhost:11434/v1"

    env_var = _ENV_VAR.get(provider)
    if env_var is None:
        return None
    api_key = os.environ.get(env_var, "").strip()
    if not api_key:
        return None
    return provider, api_key, base_url


@contextlib.contextmanager
def with_api_key(provider: str, api_key: str) -> Generator[None]:
    """Temporarily export *api_key* under the provider's expected env var.

    pydantic-ai reads credentials from the environment, so this scopes the
    key to the call rather than mutating the process for its lifetime.
    """
    env_var = _ENV_VAR.get(provider)
    if provider in _LOCAL_PROVIDERS or not env_var:
        yield
        return

    previous = os.environ.get(env_var)
    os.environ[env_var] = api_key
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous


def create_agent_model(
    provider: str,
    api_key: str = "",
    model_name: str = "",
    base_url: str = "",
) -> object:
    """Build a pydantic-ai model reference for *provider*.

    Hosted providers return a ``"provider:model"`` string, which pydantic-ai
    resolves itself.  Local providers need an explicit OpenAI-compatible
    client pointed at their base URL, with strict tool definitions disabled
    since most local models do not support them.

    Raises:
        RuntimeError: If the ``[llm]`` extra is not installed.
    """
    if provider not in _LOCAL_PROVIDERS:
        return f"{provider}:{model_name or _DEFAULT_MODEL.get(provider, 'gpt-4o-mini')}"

    try:
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(f"LLM generation needs the optional extra:\n  {LLM_INSTALL_HINT}") from exc

    openai_provider = OpenAIProvider(
        base_url=base_url or "http://localhost:11434/v1",
        api_key=api_key or "not-needed",
    )
    name = model_name or "default"

    try:
        from pydantic_ai.profiles.openai import OpenAIModelProfile

        profile = OpenAIModelProfile(openai_supports_strict_tool_definition=False)
        return OpenAIModel(name, provider=openai_provider, profile=profile)
    except ImportError:  # pragma: no cover - older pydantic-ai
        return OpenAIModel(name, provider=openai_provider)
