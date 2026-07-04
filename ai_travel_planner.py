from src.langgraph_core.LLMs.load_llms import LoadLLMs
from src.langgraph_core.graphs.travel_planner_graph import TravelGraphBuilder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.cache.redis_client import redis_client
from src.exceptions import ExceptionError
from src.loggers import Logger
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

langgraph_executor = ThreadPoolExecutor(max_workers=10)

# Initialize LLM + Graph
models = LoadLLMs()
llm = models.load_groq_model()
graph_builder = TravelGraphBuilder(llm)
graph = graph_builder.build()

logger = Logger(__name__).get_logger()


# =========================
# 🔑 MAIN CHAT HANDLER
# =========================
async def langgraph_chatbot(user_message: str, user_id: str = None, session_id: str = None):
    """
    Stateless LangGraph execution with minimal Redis persistence
    """
    try:
        logger.info(f"User({user_id}): {user_message}")

        # 1️⃣ Load persisted DECISION state only
        persisted_state = await get_user_conversation_state(user_id, session_id)

        # 2️⃣ Build fresh runtime state (NO message history)
        runtime_state = {
            "messages": [HumanMessage(content=user_message)],
            "route": persisted_state.get("route"),
            "intent": persisted_state.get("intent"),
            "entities": persisted_state.get("entities", {}),
            "awaiting_field": persisted_state.get("awaiting_field"),
        }

        new_ai_messages = []

        # 3️⃣ Run LangGraph
        async for event in graph.astream(runtime_state):
            for value in event.values():
                runtime_state.update(value)

                for msg in runtime_state.get("messages", []):
                    if isinstance(msg, AIMessage) and msg.content:
                        new_ai_messages.append(msg.content)
                    elif isinstance(msg, ToolMessage) and msg.content:
                        new_ai_messages.append(msg.content)

        # 4️⃣ Persist ONLY decision state
        new_persisted_state = {
            "route": runtime_state.get("route"),
            "intent": runtime_state.get("intent"),
            "entities": runtime_state.get("entities"),
            "awaiting_field": runtime_state.get("awaiting_field"),
            "updated_at": int(time.time())
        }

        await save_user_conversation_state(user_id, session_id, new_persisted_state)

        return "\n".join(new_ai_messages) if new_ai_messages else "No response."

    except Exception as e:
        raise ExceptionError(e)


# =========================
# REDIS STATE HANDLERS
# =========================
async def get_user_conversation_state(user_id: str, session_id: str):
    """
    Get minimal decision state from Redis
    """
    if not user_id:
        return {}

    key = f"conversation_state:{user_id}:{session_id}"
    state = await redis_client.get_json(key)

    return state or {}


async def save_user_conversation_state(user_id: str, session_id: str, state: dict):
    """
    Save ONLY decision state (no messages)
    """
    if not user_id:
        return

    key = f"conversation_state:{user_id}:{session_id}"
    # logger.info(f"Persisting state: {state}")
    print(">>>", state)
    await redis_client.set_json(key, state, expire=3600)


# =========================
# 🧪 CLI TESTING
# =========================
if __name__ == "__main__":
    print("🤖 Travel Planner Chatbot (type 'quit' to exit)\n")

    # user_id = "test_user"
    # session_id = "test_session"

    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            response = asyncio.run(
                langgraph_chatbot(user_input)
            )
            print(f"Assistant: {response}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
