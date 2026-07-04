import os
import re
import sys
from datetime import timedelta

import spacy
import yaml
from dateutil import parser as date_parser
from dotenv import find_dotenv, load_dotenv

from src.exceptions import ExceptionError
from src.loggers import logging

load_dotenv(find_dotenv())


def get_api_key(api_key_name):
    return os.environ[api_key_name]


def load_llm_config(provider_name: str, config_path=r".\src\config\llm_configs.yml"):
    """
    Load configuration for a specific LLM provider.

    Args:
        provider_name (str): e.g., "gemini", "groq", "openai".
        config_path (str): Path to YAML config file.

    Returns:
        dict: Configuration dictionary for the provider,
        or None if an error occurs.
    """
    try:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            configs = yaml.safe_load(f)
            logging.info("Read the llm releted config file")

        if not isinstance(configs, dict):
            raise ValueError(f"Invalid YAML structure in {config_path}. Expected a dictionary at root level.")

        if provider_name not in configs:
            raise ValueError(f"Provider '{provider_name}' not found in config file.")

        return configs[provider_name]
    except Exception as e:
        raise ExceptionError(e, sys)


class TravelInfo:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_md")  # good for location

    def extract_location(self, text: str):
        doc = self.nlp(text)
        locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
        return locations

    def extract_dates_and_duration(self, text: str):
        start_date, end_date, duration = None, None, None

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

        return start_date, end_date, duration

    def extract_trip_info(self, text: str):
        locations = self.extract_location(text)
        start, end, trip_days = self.extract_dates_and_duration(text)

        return {
            "destination": locations[0] if locations else None,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "duration": trip_days,
        }
