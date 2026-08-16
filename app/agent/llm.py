"""LLM provider factory - supports free-tier models only.

Supported providers:
- Google Gemini (free tier: gemini-2.0-flash, 15 RPM)
- Groq (free tier: llama-3.1-70b-versatile, mixtral-8x7b)
- Ollama (local, no API key needed)
- OpenRouter (free/paid models via OpenAI-compatible API)
"""

from langchain_core.language_models import BaseChatModel

from app.config import LLMProvider, get_settings


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    """Get the configured LLM based on environment settings.

    Args:
        temperature: Model temperature (0.0 for deterministic output in evals)

    Returns:
        LangChain chat model instance with tool-calling support.
    """
    settings = get_settings()

    if settings.llm_provider == LLMProvider.GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey"
            )

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
        )

    elif settings.llm_provider == LLMProvider.GROQ:
        from langchain_groq import ChatGroq

        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get a free key at https://console.groq.com/keys"
            )

        return ChatGroq(
            model=settings.groq_model,
            groq_api_key=settings.groq_api_key,
            temperature=temperature,
            model_kwargs={"parallel_tool_calls": False},
        )

    elif settings.llm_provider == LLMProvider.OLLAMA:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
        )

    elif settings.llm_provider == LLMProvider.OPENROUTER:
        from langchain_openai import ChatOpenAI

        if not settings.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Get a key at https://openrouter.ai/keys"
            )

        return ChatOpenAI(
            model=settings.openrouter_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
        )

    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
