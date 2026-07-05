import asyncio
import time
from functools import lru_cache
from threading import Lock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.cache.redis_client import redis_client
from src.exceptions import ExceptionError
from src.langgraph_core.graphs.travel_planner_graph import TravelGraphBuilder
from src.langgraph_core.LLMs.load_llms import LoadLLMs
from src.loggers import Logger
from src.utils.state_utils import extract_persisted_state, merge_persisted_state

logger = Logger(__name__).get_logger()

CONVERSATION_STATE_TTL = 86400  # 24 hours, aligned with session cookie

# Thread-safe lazy initialization for LLM and graph
_llm_instance = None
_graph_instance = None
_init_lock = Lock()


def _get_llm():
    """Lazy load LLM with thread-safe initialization."""
    global _llm_instance
    if _llm_instance is None:
        with _init_lock:
            if _llm_instance is None:
                logger.info("Initializing LLM (lazy loading)")
                models = LoadLLMs()
                _llm_instance = models.load_groq_model()
    return _llm_instance


def _get_graph():
    """Lazy load graph with thread-safe initialization."""
    global _graph_instance
    if _graph_instance is None:
        with _init_lock:
            if _graph_instance is None:
                logger.info("Building travel planner graph (lazy loading)")
                llm = _get_llm()
                graph_builder = TravelGraphBuilder(llm)
                _graph_instance = graph_builder.build()
    return _graph_instance


async def langgraph_chatbot(user_message: str, user_id: str = None, session_id: str = None):
    """Run the travel planner graph with full workflow state persisted in Redis."""
    try:
        if not user_message or not str(user_message).strip():
            return "Please enter a message."

        logger.info("User(%s): %s", user_id, user_message)

        persisted_state = await get_user_conversation_state(user_id, session_id)
        runtime_state = merge_persisted_state(persisted_state, user_message.strip())
        initial_message_count = len(runtime_state.get("messages", []))

        # Use lazy-loaded graph
        graph = _get_graph()

        async for event in graph.astream(runtime_state):
            for value in event.values():
                runtime_state.update(value)

        new_ai_messages = []
        for msg in runtime_state.get("messages", [])[initial_message_count:]:
            if isinstance(msg, AIMessage) and msg.content:
                new_ai_messages.append(str(msg.content))
            elif isinstance(msg, ToolMessage) and msg.content:
                new_ai_messages.append(str(msg.content))

        persisted = extract_persisted_state(runtime_state)
        persisted["updated_at"] = int(time.time())
        await save_user_conversation_state(user_id, session_id, persisted)

        return "\n".join(new_ai_messages) if new_ai_messages else "No response."

    except Exception as e:
        logger.error("LangGraph chatbot error: %s", e, exc_info=True)
        raise ExceptionError(e)


async def get_user_conversation_state(user_id: str, session_id: str) -> dict:
    if not user_id or not session_id:
        return {}

    key = f"conversation_state:{user_id}:{session_id}"
    state = await redis_client.get_json(key)
    return state or {}


async def save_user_conversation_state(user_id: str, session_id: str, state: dict):
    if not user_id or not session_id:
        return

    key = f"conversation_state:{user_id}:{session_id}"
    await redis_client.set_json(key, state, expire=CONVERSATION_STATE_TTL)


if __name__ == "__main__":
    print("Travel Planner Chatbot (type 'quit' to exit)\n")
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            response = asyncio.run(langgraph_chatbot(user_input, user_id="cli_user", session_id="cli_session"))
            print(f"Assistant: {response}")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
