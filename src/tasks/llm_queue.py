import asyncio
import redis.asyncio as redis
from celery import Celery
from langchain_core.messages import HumanMessage
from src.config.settings import settings
from src.loggers import Logger

logger = Logger(__name__).get_logger()

# Celery app for background processing
llm_app = Celery('llm_tasks', broker=settings.REDIS_URL)

# Configure queues and rate limiting
llm_app.conf.update(
    task_routes={
        'tasks.llm_queue.process_llm_request': {'queue': 'llm'},
        'tasks.llm_queue.process_tool_call': {'queue': 'tools'},
    },
    task_annotations={
        'process_llm_request': {'rate_limit': '1000/m'},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True
)

# In-memory LLM cache to avoid re-initialization
_llm_cache = {}

def get_llm(provider: str):
    """Get LLM instance with caching"""
    if provider in _llm_cache:
        return _llm_cache[provider]

    from src.langgraph_core.LLMs.load_llms import LoadLLMs
    models = LoadLLMs()

    if provider == "groq":
        llm = models.load_groq_model()
    elif provider == "gemini":
        llm = models.load_gemini_model()
    elif provider == "openai":
        llm = models.load_openai_model()
    else:
        llm = models.load_groq_model()  # default

    _llm_cache[provider] = llm
    return llm

@llm_app.task
def process_llm_request(prompt: str, provider: str = "groq"):
    """Process LLM calls in background workers"""
    try:
        llm = get_llm(provider)

        # Run async function in sync context
        async def run_llm():
            return await llm.ainvoke([HumanMessage(content=prompt)])

        # Execute async function in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(run_llm())
        loop.close()

        return response.content

    except Exception as e:
        logger.error(f"LLM task error: {e}")
        return f"Error processing request: {str(e)}"

@llm_app.task
def process_tool_call(tool_name: str, tool_args: dict):
    """Process tool calls in background"""
    try:
        from src.langgraph_core.tools.custom_tools import (
            weather_information, search_flights, search_hotels
        )

        tools = {
            "weather_information": weather_information,
            "search_flights": search_flights,
            "search_hotels": search_hotels
        }

        if tool_name in tools:
            # Run async tool function
            async def run_tool():
                return await tools[tool_name](**tool_args)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(run_tool())
            loop.close()

            return result
        else:
            return {"error": f"Tool {tool_name} not found"}

    except Exception as e:
        logger.error(f"Tool task error: {e}")
        return {"error": str(e)}
