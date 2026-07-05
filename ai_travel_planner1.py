from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.cache.redis_cluster import redis_cluster
from src.exceptions import ExceptionError
from src.loggers import Logger
from tasks.task_manager import task_manager
import asyncio
import threading

# Lazy LLM and Graph initialization
_llm = None
_graph = None
_init_lock = threading.Lock()


def _get_llm():
    """Lazy load LLM with thread safety"""
    global _llm
    if _llm is None:
        with _init_lock:
            if _llm is None:
                from src.langgraph_core.LLMs.load_llms import LoadLLMs
                models = LoadLLMs()
                _llm = models.load_groq_model()
    return _llm


def _get_graph():
    """Lazy load graph with thread safety"""
    global _graph
    if _graph is None:
        with _init_lock:
            if _graph is None:
                from src.langgraph_core.graphs.travel_planner_graph import TravelGraphBuilder
                graph_builder = TravelGraphBuilder(_get_llm())
                _graph = graph_builder.build()
    return _graph


logger = Logger(__name__).get_logger()

async def langgraph_chatbot(user_message: str, user_id: str = None, session_id: str = None):
    """Handle user message with user-specific state and queued processing"""
    try:
        logger.info(f"User message from user {user_id}: {user_message}")

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

        # Process through LangGraph
        async def run_langgraph():
            new_ai_messages = []

            async for event in _get_graph().astream(conversation_state):
                for value in event.values():
                    conversation_state.update(value)

                    # Get ALL messages from current state
                    all_messages = conversation_state.get("messages", [])

                    # Extract only NEW messages added during this execution
                    if initial_message_count < len(all_messages):
                        new_messages = all_messages[initial_message_count:]

                        for msg in new_messages:
                            if isinstance(msg, AIMessage) and msg.content:
                                logger.info(f"Assistant: {msg.content}")
                                new_ai_messages.append(msg.content)
                            elif isinstance(msg, ToolMessage) and msg.content:
                                logger.info(f"[Tool Result] {msg.content}")
                                new_ai_messages.append(msg.content)
            return new_ai_messages, conversation_state

        new_ai_messages, updated_state = await run_langgraph()

        serializable_state = convert_state_to_serializable(updated_state)

        # ASYNC STATE SAVING
        await save_user_conversation_state(user_id, session_id, serializable_state)

        # Return only NEW messages from this execution
        return "\n".join(new_ai_messages) if new_ai_messages else "No response."

    except Exception as e:
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
    if not user_id:
        return None

    key = f"conversation_state:{user_id}:{session_id}"
    serialized_state = await redis_cluster.get_json(key)

    if serialized_state:
        return convert_state_from_serializable(serialized_state)

    return None

async def save_user_conversation_state(user_id: str, session_id: str, state: dict):
    """Async save user-specific conversation state to Redis"""
    if not user_id:
        return

    key = f"conversation_state:{user_id}:{session_id}"
    await redis_cluster.set_json(key, state, expire=3600)

if __name__ == "__main__":
    print("🤖 Travel Planner Chatbot (type 'quit' to exit)\n")
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            asyncio.run(langgraph_chatbot(user_input))
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
