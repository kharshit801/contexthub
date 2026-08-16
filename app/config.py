"""Application configuration using pydantic-settings."""

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM
    llm_provider: LLMProvider = LLMProvider.GEMINI

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct:free"

    # Database
    database_url: str = "postgresql://contexthub:contexthub@127.0.0.1:5433/contexthub"
    database_url_readonly: str = "postgresql://contexthub_readonly:contexthub@127.0.0.1:5433/contexthub"

    # App
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
