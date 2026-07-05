"""Lazy-loading LLM manager with model caching for production use."""

import sys
import threading
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from src.exceptions import ExceptionError
from src.loggers import logging
from src.utils.Utilities import get_api_key, load_llm_config


class LoadLLMs:
    """Thread-safe lazy-loading LLM manager with model caching.

    Models are loaded on first access and cached for subsequent calls.
    Uses double-checked locking for thread safety.
    """

    _instance: Optional["LoadLLMs"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "LoadLLMs":
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize only once (lazy API key loading)."""
        if self._initialized:
            return

        self._initialized = True
        self._models_lock = threading.Lock()
        self._models_cache: dict[str, object] = {}

        # Lazy API key loading - only load when needed
        self._api_keys: dict[str, Optional[str]] = {
            "groq": None,
            "gemini": None,
            "openai": None,
        }

        # Lazy config loading
        self._configs: dict[str, Optional[dict]] = {
            "gemini": None,
            "groq": None,
            "openai": None,
            "deepseek": None,
        }

    def _get_api_key(self, key_name: str) -> str:
        """Lazily load and cache API key."""
        if self._api_keys.get(key_name) is None:
            with self._lock:
                if self._api_keys.get(key_name) is None:
                    self._api_keys[key_name] = get_api_key(key_name)
        return self._api_keys[key_name]

    def _get_config(self, config_name: str) -> dict:
        """Lazily load and cache LLM config."""
        if self._configs.get(config_name) is None:
            with self._lock:
                if self._configs.get(config_name) is None:
                    self._configs[config_name] = load_llm_config(config_name)
        return self._configs[config_name]

    def _get_cached_model(self, model_type: str, loader_func) -> object:
        """Get model from cache or load it (thread-safe)."""
        if model_type not in self._models_cache:
            with self._models_lock:
                if model_type not in self._models_cache:
                    logging.info(f"Loading {model_type} model (lazy)...")
                    self._models_cache[model_type] = loader_func()
                    logging.info(f"{model_type} model cached successfully")
        return self._models_cache[model_type]

    @property
    def groq_key(self) -> str:
        """Lazily get Groq API key."""
        return self._get_api_key("GROQ_API_KEY")

    @property
    def gemini_key(self) -> str:
        """Lazily get Gemini API key."""
        return self._get_api_key("GOOGLE_API_KEY")

    @property
    def openai_key(self) -> str:
        """Lazily get OpenAI API key."""
        return self._get_api_key("OPENAI_API_KEY")

    @property
    def gemini_config(self) -> dict:
        """Lazily get Gemini config."""
        return self._get_config("gemini")

    @property
    def groq_config(self) -> dict:
        """Lazily get Groq config."""
        return self._get_config("groq")

    @property
    def openai_config(self) -> dict:
        """Lazily get OpenAI config."""
        return self._get_config("openai")

    @property
    def deepseek_config(self) -> dict:
        """Lazily get Deepseek config."""
        return self._get_config("deepseek")

    def load_groq_model(self) -> ChatGroq:
        """Load and cache Groq model."""
        try:
            def _load():
                return ChatGroq(
                    api_key=self.groq_key,
                    model=self.groq_config["model_name"],
                    temperature=self.groq_config["temperature"],
                    max_tokens=self.groq_config["max_tokens"],
                    timeout=self.groq_config.get("timeout", 60),
                    max_retries=self.groq_config.get("max_retries", 3),
                )
            return self._get_cached_model("groq", _load)
        except Exception as e:
            logging.error(f"Failed to load Groq model: {e}")
            raise ExceptionError(e, sys)

    def load_gemini_model(self) -> ChatGoogleGenerativeAI:
        """Load and cache Gemini model."""
        try:
            def _load():
                return ChatGoogleGenerativeAI(
                    model=self.gemini_config["model_name"],
                    temperature=self.gemini_config["temperature"],
                    max_tokens=self.gemini_config["max_tokens"],
                    timeout=self.gemini_config.get("timeout", 60),
                    max_retries=self.gemini_config.get("max_retries", 3),
                    google_api_key=self.gemini_key,
                )
            return self._get_cached_model("gemini", _load)
        except Exception as e:
            logging.error(f"Failed to load Gemini model: {e}")
            raise ExceptionError(e, sys)

    def load_openai_model(self) -> ChatOpenAI:
        """Load and cache OpenAI model."""
        try:
            def _load():
                return ChatOpenAI(
                    api_key=self.openai_key,
                    model=self.openai_config["model_name"],
                    temperature=self.openai_config["temperature"],
                    max_tokens=self.openai_config["max_tokens"],
                    timeout=self.openai_config.get("timeout", 60),
                    max_retries=self.openai_config.get("max_retries", 3),
                )
            return self._get_cached_model("openai", _load)
        except Exception as e:
            logging.error(f"Failed to load OpenAI model: {e}")
            raise ExceptionError(e, sys)

    def load_deepseek_model(self) -> ChatGroq:
        """Load and cache Deepseek model."""
        try:
            def _load():
                return ChatGroq(
                    api_key=self.groq_key,
                    model=self.deepseek_config["model_name"],
                    temperature=self.deepseek_config["temperature"],
                    max_tokens=self.deepseek_config["max_tokens"],
                    timeout=self.deepseek_config.get("timeout", 60),
                    max_retries=self.deepseek_config.get("max_retries", 3),
                )
            return self._get_cached_model("deepseek", _load)
        except Exception as e:
            logging.error(f"Failed to load Deepseek model: {e}")
            raise ExceptionError(e, sys)

    def get_model(self, model_type: str = "groq") -> object:
        """Get model by type with lazy loading."""
        model_loaders = {
            "groq": self.load_groq_model,
            "gemini": self.load_gemini_model,
            "openai": self.load_openai_model,
            "deepseek": self.load_deepseek_model,
        }

        if model_type not in model_loaders:
            raise ValueError(f"Unknown model type: {model_type}. Available: {list(model_loaders.keys())}")

        return model_loaders[model_type]()

    def clear_cache(self) -> None:
        """Clear cached models (useful for testing or hot-reload)."""
        with self._models_lock:
            self._models_cache.clear()
        logging.info("LLM model cache cleared")

    def preload_all_models(self) -> None:
        """Preload all models eagerly (optional, for warm-up)."""
        logging.info("Preloading all LLM models...")
        self.load_groq_model()
        self.load_gemini_model()
        self.load_openai_model()
        self.load_deepseek_model()
        logging.info("All LLM models preloaded")


# Module-level convenience functions for lazy access
_llm_manager: Optional[LoadLLMs] = None


def get_llm_manager() -> LoadLLMs:
    """Get singleton LLM manager instance."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LoadLLMs()
    return _llm_manager


def get_model(model_type: str = "groq") -> object:
    """Convenience function to get a lazy-loaded model."""
    return get_llm_manager().get_model(model_type)
