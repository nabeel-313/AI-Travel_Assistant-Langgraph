"""
Utility functions for the Travel AI Assistant.
Includes API key loading, LLM config loading, and NLP extraction.
"""
import os
import re
import sys
from datetime import timedelta
from functools import lru_cache
from typing import Dict, Any, Optional, List, Tuple

import spacy
import yaml
from dateutil import parser as date_parser
from dotenv import find_dotenv, load_dotenv

from src.loggers import Logger

logger = Logger(__name__).get_logger()

# Load environment variables
load_dotenv(find_dotenv())


def get_api_key(api_key_name: str, required: bool = True) -> str:
    """
    Get API key from environment variables.

    Args:
        api_key_name: Name of the environment variable
        required: Whether the key is required

    Returns:
        API key value

    Raises:
        ValueError: If required key is not found
    """
    api_key = os.environ.get(api_key_name, "").strip()

    if not api_key and required:
        logger.error(f"Required API key not found: {api_key_name}")
        raise ValueError(f"Required API key not configured: {api_key_name}")

    if not api_key:
        logger.warning(f"Optional API key not found: {api_key_name}")

    return api_key


@lru_cache(maxsize=1)
def load_llm_config(provider_name: str, config_path: str = r".\src\config\llm_configs.yml") -> Dict[str, Any]:
    """
    Load configuration for a specific LLM provider.
    Results are cached for performance.

    Args:
        provider_name: LLM provider name (e.g., "gemini", "groq", "openai")
        config_path: Path to YAML config file

    Returns:
        Configuration dictionary for the provider

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If provider not found or invalid YAML
    """
    try:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            configs = yaml.safe_load(f)

        if not isinstance(configs, dict):
            raise ValueError(f"Invalid YAML structure in {config_path}. Expected a dictionary at root level.")

        if provider_name not in configs:
            available = ", ".join(configs.keys()) if configs else "none"
            raise ValueError(
                f"Provider '{provider_name}' not found in config file. Available: {available}"
            )

        logger.info(f"Loaded LLM config for provider: {provider_name}")
        return configs[provider_name]

    except FileNotFoundError:
        raise
    except ValueError:
        raise
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        logger.error(f"Error loading LLM config: {e}")
        raise ValueError(f"Failed to load LLM config: {e}")


class TravelInfo:
    """
    NLP-based travel information extraction.
    Uses spaCy for entity recognition and date parsing.
    """

    _nlp_model: Optional[Any] = None
    _model_name: str = "en_core_web_md"

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize TravelInfo with optional custom model.

        Args:
            model_name: Optional spaCy model name to use
        """
        if model_name:
            self._model_name = model_name
        self._load_model()

    def _load_model(self) -> None:
        """Load spaCy model with error handling."""
        if TravelInfo._nlp_model is not None:
            return

        try:
            TravelInfo._nlp_model = spacy.load(self._model_name)
            logger.info(f"Loaded spaCy model: {self._model_name}")
        except OSError:
            logger.warning(
                f"Model '{self._model_name}' not found. "
                f"Download with: python -m spacy download {self._model_name}"
            )
            # Try smaller model as fallback
            try:
                TravelInfo._nlp_model = spacy.load("en_core_web_sm")
                logger.info("Using fallback model: en_core_web_sm")
            except OSError:
                logger.error("No spaCy models available. NLP features will be limited.")
                TravelInfo._nlp_model = None

    @property
    def nlp(self):
        """Get the NLP model, loading if necessary."""
        if TravelInfo._nlp_model is None:
            self._load_model()
        return TravelInfo._nlp_model

    def extract_location(self, text: str) -> List[str]:
        """
        Extract geographic locations from text.

        Args:
            text: Input text to analyze

        Returns:
            List of location names found
        """
        if not self.nlp:
            logger.warning("NLP model not available, returning empty list")
            return []

        try:
            doc = self.nlp(text)
            locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
            return locations
        except Exception as e:
            logger.error(f"Error extracting locations: {e}")
            return []

    def extract_dates_and_duration(self, text: str) -> Tuple[Optional[Any], Optional[Any], Optional[int]]:
        """
        Extract travel dates and duration from text.

        Args:
            text: Input text to analyze

        Returns:
            Tuple of (start_date, end_date, duration_days)
        """
        start_date, end_date, duration = None, None, None

        try:
            # Case 1: explicit date range "from X to Y"
            range_match = re.search(
                r"from\s+([\d]{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s+to\s+([\d]{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
                text,
                re.IGNORECASE,
            )
            if range_match:
                start_date = date_parser.parse(range_match.group(1)).date()
                end_date = date_parser.parse(range_match.group(2)).date()
                duration = (end_date - start_date).days
                return start_date, end_date, duration

            # Case 2: single start date with duration
            date_match = re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b", text)
            if date_match:
                start_date = date_parser.parse(date_match.group()).date()

            dur_match = re.search(r"(\d+)\s+days?", text.lower())
            if dur_match:
                duration = int(dur_match.group(1))

            if start_date and duration:
                end_date = start_date + timedelta(days=duration)

        except Exception as e:
            logger.error(f"Error extracting dates: {e}")

        return start_date, end_date, duration

    def extract_trip_info(self, text: str) -> Dict[str, Any]:
        """
        Extract complete trip information from text.

        Args:
            text: Input text to analyze

        Returns:
            Dictionary with destination, dates, and duration
        """
        locations = self.extract_location(text)
        start, end, trip_days = self.extract_dates_and_duration(text)

        return {
            "destination": locations[0] if locations else None,
            "destinations": locations,  # All locations found
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "duration": trip_days,
        }


# Singleton instance for convenience
_travel_info_instance: Optional[TravelInfo] = None


def get_travel_info() -> TravelInfo:
    """
    Get singleton TravelInfo instance.

    Returns:
        TravelInfo instance
    """
    global _travel_info_instance
    if _travel_info_instance is None:
        _travel_info_instance = TravelInfo()
    return _travel_info_instance
