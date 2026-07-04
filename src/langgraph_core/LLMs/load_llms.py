import sys

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from src.exceptions import ExceptionError
from src.loggers import logging
from src.utils.Utilities import get_api_key, load_llm_config


class LoadLLMs:
    def __init__(self):
        # load llm api keys
        self.groq_key = get_api_key("GROQ_API_KEY")
        self.gemini_key = get_api_key("GOOGLE_API_KEY")
        self.openai_key = get_api_key("OPENAI_API_KEY")

        # read llm related configs
        self.gemini_config = load_llm_config("gemini")
        self.groq_config = load_llm_config("groq")
        self.openai_config = load_llm_config("openai")
        self.deppseek_config = load_llm_config("deepseek")

    def load_groq_model(self):
        try:
            logging.info("Loading Groq model...")
            groq_llm = ChatGroq(
                api_key=self.groq_key,
                model=self.groq_config["model_name"],
                temperature=self.groq_config["temperature"],
                max_tokens=self.groq_config["max_tokens"],
                timeout=self.groq_config["timeout"],
                max_retries=self.groq_config["max_retries"],
            )
            logging.info(f"Groq model loaded successfully and mode is {self.groq_config["model_name"]} ")
            return groq_llm
        except Exception as e:
            raise ExceptionError(e, sys)

    def load_gemini_model(self):
        try:
            logging.info("Loading Gemini model...")
            gemini_llm = ChatGoogleGenerativeAI(
                model=self.gemini_config["model_name"],
                temperature=self.gemini_config["temperature"],
                max_tokens=self.gemini_config["max_tokens"],
                timeout=self.gemini_config["timeout"],
                max_retries=self.gemini_config["max_retries"],
            )
            logging.info(f"Gemini LLM loaded successfully  and model is {self.gemini_config["model_name"]}")
            return gemini_llm
        except Exception as e:
            raise ExceptionError(e, sys)

    def load_openai_model(self):
        try:
            logging.info("Loading OpenAI model...")
            openai_llm = ChatOpenAI(
                api_key=self.openai_key,
                model=self.openai_config["model_name"],
                temperature=self.openai_config["temperature"],
                max_tokens=self.openai_config["max_tokens"],
                timeout=self.openai_config["timeout"],
                max_retries=self.openai_config["max_retries"],
            )
            logging.info(f"OpenAI LLM loaded successfully and model is {self.openai_config['model_name']}")
            return openai_llm
        except Exception as e:
            raise ExceptionError(e, sys)

    def load_deppseek_model(self):
        try:
            logging.info("Loading Deepseek model...")
            deepseek_llm = ChatGroq(
                api_key=self.groq_key,
                model=self.deppseek_config["model_name"],
                temperature=self.deppseek_config["temperature"],
                max_tokens=self.deppseek_config["max_tokens"],
                timeout=self.deppseek_config["timeout"],
                max_retries=self.deppseek_config["max_retries"],
            )
            logging.info(f"Deepseek LLM loaded successfully and model is {self.deppseek_config['model_name']}")
            return deepseek_llm

        except Exception as e:
            raise ExceptionError(e, sys)
