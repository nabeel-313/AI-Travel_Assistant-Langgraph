from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.cache.redis_cluster import redis_cluster
from src.exceptions import ExceptionError
from src.loggers import Logger
import asyncio
import time
from typing import Optional

CONVERSATION_STATE_TTL = 86400  # 24 hours, aligned with session cookie

# Lazy LLM and Graph initialization (pre-loaded at module import to avoid async lock issues)
_llm = None
_graph = None
# FIXED — lazy-create the lock inside the event loop:
_init_lock: Optional[asyncio.Lock] = None

def _get_init_lock() -> asyncio.Lock:
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


def _get_llm_sync():
    """Synchronously load LLM (called during module init or first sync use)"""
    global _llm
    if _llm is None:
        from src.langgraph_core.LLMs.load_llms import LoadLLMs
        models = LoadLLMs()
        _llm = models.load_groq_model()
    return _llm


async def _get_llm():
    """Async-safe lazy load LLM.
    NOTE: Do NOT call this while holding _get_init_lock() — use inline loading instead.
    """
    global _llm
    if _llm is None:
        async with _get_init_lock():
            if _llm is None:
                from src.langgraph_core.LLMs.load_llms import LoadLLMs
                models = LoadLLMs()
                _llm = models.load_groq_model()
    return _llm


async def _get_graph():
    """Async-safe lazy load graph"""
    global _graph, _llm
    async with _get_init_lock():
        if _graph is None:
            from src.langgraph_core.graphs.travel_planner_graph import TravelGraphBuilder
            # Load LLM inline WITHOUT re-acquiring the lock
            if _llm is None:
                from src.langgraph_core.LLMs.load_llms import LoadLLMs
                models = LoadLLMs()
                _llm = models.load_groq_model()
            graph_builder = TravelGraphBuilder(_llm)
            _graph = graph_builder.build()
    return _graph


logger = Logger(__name__).get_logger()

async def langgraph_chatbot(user_message: str, user_id: str = None, session_id: str = None):
    """Handle user message with user-specific state and queued processing"""
    try:
        if not user_message or not str(user_message).strip():
            return "Please enter a message."

        logger.info("User(%s): %s", user_id, user_message)

        # ASYNC STATE RETRIEVAL
        conversation_state = await get_user_conversation_state(user_id, session_id)

        if not conversation_state:
            conversation_state = {
                "user_id": user_id,
                "session_id": session_id,
                "messages": [],
                "route": "router_node"
            }

        initial_message_count = len(conversation_state.get("messages", []))

        # Add user message to persisted state
        conversation_state["messages"].append(HumanMessage(content=user_message))

        # Use lazy-loaded graph (async-safe)
        graph = await _get_graph()

        # Add overall timeout for graph execution (60 seconds)
        try:
            async for event in asyncio.wait_for(
                graph.astream(conversation_state),
                timeout=60.0
            ):
                for value in event.values():
                    conversation_state.update(value)
        except asyncio.TimeoutError:
            logger.error("Graph execution timed out after 60 seconds")
            return "I'm sorry, the request took too long to process. Please try again with a simpler query."

        new_ai_messages = []
        for msg in conversation_state.get("messages", [])[initial_message_count:]:
            if isinstance(msg, AIMessage) and msg.content:
                logger.info("Assistant: %s", msg.content)
                new_ai_messages.append(str(msg.content))
            elif isinstance(msg, ToolMessage) and msg.content:
                logger.info("[Tool Result] %s", msg.content)
                new_ai_messages.append(str(msg.content))

        serializable_state = convert_state_to_serializable(conversation_state)
        serializable_state["updated_at"] = int(time.time())

        # ASYNC STATE SAVING
        await save_user_conversation_state(user_id, session_id, serializable_state)

        # Return only NEW messages from this execution
        return "\n".join(new_ai_messages) if new_ai_messages else "No response."

    except asyncio.TimeoutError:
        logger.error("LangGraph chatbot overall timeout for user(%s)", user_id)
        return "I'm sorry, the request took too long to process. Please try again with a simpler query."
    except Exception as e:
        logger.error("LangGraph chatbot error for user(%s): %s", user_id, e, exc_info=True)
        # Try to save state even on error so conversation isn't lost
        try:
            if 'conversation_state' in dir() and conversation_state:
                serializable_state = convert_state_to_serializable(conversation_state)
                serializable_state["updated_at"] = int(time.time())
                await save_user_conversation_state(user_id, session_id, serializable_state)
        except Exception as save_err:
            logger.error("Failed to save state after error: %s", save_err)
        raise ExceptionError(e)

def convert_state_to_serializable(state: dict) -> dict:
    """Convert LangChain messages to serializable format"""
    serializable_state = state.copy()

    if "messages" in serializable_state:
        serializable_state["messages"] = []
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                msg_dict = {"type": "human", "content": msg.content}
            elif isinstance(msg, AIMessage):
                msg_dict = {"type": "ai", "content": msg.content}
            elif isinstance(msg, ToolMessage):
                msg_dict = {"type": "tool", "content": msg.content}
            else:
                msg_dict = {"type": "human", "content": str(msg.content)}

            serializable_state["messages"].append(msg_dict)

    return serializable_state

def convert_state_from_serializable(serializable_state: dict) -> dict:
    """Convert serialized format back to LangChain messages"""
    state = serializable_state.copy()

    if "messages" in state:
        message_objects = []
        for msg_dict in state["messages"]:
            if msg_dict["type"] == "human":
                message_objects.append(HumanMessage(content=msg_dict["content"]))
            elif msg_dict["type"] == "ai":
                message_objects.append(AIMessage(content=msg_dict["content"]))
            elif msg_dict["type"] == "tool":
                message_objects.append(ToolMessage(content=msg_dict["content"]))
            else:
                message_objects.append(HumanMessage(content=msg_dict["content"]))

        state["messages"] = message_objects

    return state

async def get_user_conversation_state(user_id: str, session_id: str):
    """Async get user-specific conversation state from Redis"""
    if not user_id or not session_id:
        return {}

    key = f"conversation_state:{user_id}:{session_id}"
    serialized_state = await redis_cluster.get_json(key)

    if serialized_state:
        return convert_state_from_serializable(serialized_state)

    return {}

async def save_user_conversation_state(user_id: str, session_id: str, state: dict):
    """Async save user-specific conversation state to Redis"""
    if not user_id or not session_id:
        return

    key = f"conversation_state:{user_id}:{session_id}"
    await redis_cluster.set_json(key, state, expire=CONVERSATION_STATE_TTL)

if __name__ == "__main__":
    print("🤖 Travel Planner Chatbot (type 'quit' to exit)\n")
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            response = asyncio.run(langgraph_chatbot(user_input))
            print(f"Assistant: {response}\n")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            logger.error("Error in chat loop: %s", e, exc_info=True)
            print(f"Error: {e}")
