"""
Travel Planner Graph with checkpointing and async support.
"""
import logging
from typing import Optional, Dict, Any
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from src.langgraph_core.nodes.travel_planner_nodes import TravelPlannerNode
from src.langgraph_core.state.travel_planner_states import TravelPlannerState
from src.langgraph_core.tools.custom_tools import weather_tool
from src.langgraph_core.tools.tools import create_tool_node, get_tools

logger = logging.getLogger(__name__)


class TravelGraphBuilder:
    """
    Builder for the Travel Planner graph with checkpointing support.

    Features:
    - Checkpointing for conversation state persistence
    - Async support for non-blocking execution
    - Lazy LLM initialization
    """

    _instance: Optional['TravelGraphBuilder'] = None
    _compiled_graph: Optional[Any] = None
    _checkpointer: Optional[MemorySaver] = None

    def __new__(cls, llm=None):
        """Singleton pattern with lazy initialization."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, llm=None):
        """Initialize the graph builder with optional LLM."""
        if self._initialized and llm is None:
            return

        self._llm = llm
        self._graph_builder: Optional[StateGraph] = None
        self._travel_planner_node: Optional[TravelPlannerNode] = None
        self._initialized = True

        logger.info("TravelGraphBuilder initialized")

    @property
    def llm(self):
        """Lazy LLM property."""
        if self._llm is None:
            from src.langgraph_core.LLMs.load_llms import get_model
            self._llm = get_model()
            logger.info("LLM lazily loaded in TravelGraphBuilder")
        return self._llm

    @llm.setter
    def llm(self, value):
        """Set LLM."""
        self._llm = value

    @classmethod
    def get_checkpointer(cls) -> MemorySaver:
        """Get or create the checkpointer singleton."""
        if cls._checkpointer is None:
            cls._checkpointer = MemorySaver()
            logger.info("Created MemorySaver checkpointer")
        return cls._checkpointer

    @classmethod
    def clear_checkpointer(cls) -> None:
        """Clear the checkpointer (useful for testing)."""
        if cls._checkpointer is not None:
            cls._checkpointer = None
            logger.info("Checkpointer cleared")

    def _add_nodes(self) -> None:
        """Register all nodes in the graph."""
        self._travel_planner_node = TravelPlannerNode(self.llm)

        self._graph_builder.add_node("router_node", self._travel_planner_node.router)
        self._graph_builder.add_node("chat_node", self._travel_planner_node.chat_node)

        # Tool nodes
        weather_node = ToolNode(tools=[weather_tool])
        self._graph_builder.add_node("weather_node", weather_node)

        tools = get_tools()
        search_node = create_tool_node(tools)
        self._graph_builder.add_node("search_node", search_node)

        # Travel planning nodes
        self._graph_builder.add_node("travel_node", self._travel_planner_node.travel_node)
        self._graph_builder.add_node("collect_missing_travel_info_node", self._travel_planner_node.collect_missing_travel_info)
        self._graph_builder.add_node("process_travel_confirmation_node", self._travel_planner_node.process_travel_confirmation)
        self._graph_builder.add_node("flight_search_node", self._travel_planner_node.flight_search_node)
        self._graph_builder.add_node("flight_selection_node", self._travel_planner_node.flight_selection_node)
        self._graph_builder.add_node("hotel_search_node", self._travel_planner_node.hotel_search_node)
        self._graph_builder.add_node("hotel_selection_node", self._travel_planner_node.hotel_selection_node)
        self._graph_builder.add_node("collect_hotel_info_node", self._travel_planner_node.collect_hotel_info_node)
        self._graph_builder.add_node("generate_itinerary_node", self._travel_planner_node.generate_itinerary_node)

        logger.info("All nodes registered in graph")

    def _add_edges(self) -> None:
        """Register all edges in the graph."""
        # Start with router
        self._graph_builder.add_edge(START, "router_node")

        # Router decisions
        self._graph_builder.add_conditional_edges(
            "router_node",
            lambda state: state.get("route"),
            {
                "process_travel_confirmation": "process_travel_confirmation_node",
                "collect_missing_travel_info_node": "collect_missing_travel_info_node",
                "flight_search_node": "flight_search_node",
                "flight_selection_node": "flight_selection_node",
                "collect_hotel_info_node": "collect_hotel_info_node",
                "hotel_search_node": "hotel_search_node",
                "hotel_selection_node": "hotel_selection_node",
                "generate_itinerary_node": "generate_itinerary_node",
                "travel": "travel_node",
                "weather": "weather_node",
                "search": "search_node",
                "chat": "chat_node",
            },
        )

        # Travel flow
        self._graph_builder.add_conditional_edges(
            "travel_node",
            lambda state: state.get("route", "chat"),
            {
                "collect_missing_travel_info_node": "collect_missing_travel_info_node",
                "flight_search_node": "flight_search_node",
                "chat": "chat_node",
            },
        )

        # Missing info collection
        self._graph_builder.add_conditional_edges(
            "collect_missing_travel_info_node",
            lambda state: state.get("route", "END"),
            {
                "process_travel_confirmation": "process_travel_confirmation_node",
                "END": END,
            },
        )

        # Travel confirmation flow
        self._graph_builder.add_conditional_edges(
            "process_travel_confirmation_node",
            lambda state: state.get("route", "END"),
            {
                "flight_search_node": "flight_search_node",
                "chat_node": "chat_node",
                "END": END,
            },
        )

        # Flight search to selection flow
        self._graph_builder.add_conditional_edges(
            "flight_search_node",
            lambda state: state.get("route", "END"),
            {
                "flight_selection_node": "flight_selection_node",
                "hotel_search_node": "hotel_search_node",
                "END": END,
            },
        )

        self._graph_builder.add_conditional_edges(
            "flight_selection_node",
            lambda state: state.get("route", "END"),
            {
                "hotel_search_node": "hotel_search_node",
                "END": END,
            },
        )

        # Hotel search to selection flow
        self._graph_builder.add_conditional_edges(
            "hotel_search_node",
            lambda state: state.get("route", "END"),
            {
                "collect_hotel_info_node": "collect_hotel_info_node",
                "hotel_selection_node": "hotel_selection_node",
                "END": END,
            },
        )

        # Hotel info collection flow
        self._graph_builder.add_conditional_edges(
            "collect_hotel_info_node",
            lambda state: state.get("route", "END"),
            {
                "collect_hotel_info_node": "collect_hotel_info_node",
                "hotel_search_node": "hotel_search_node",
                "END": END,
            },
        )

        # Hotel selection flow
        self._graph_builder.add_conditional_edges(
            "hotel_selection_node",
            lambda state: state.get("route", "END"),
            {
                "generate_itinerary_node": "generate_itinerary_node",
                "hotel_selection_node": "hotel_selection_node",
                "END": END,
            },
        )

        # End points
        self._graph_builder.add_edge("chat_node", END)
        self._graph_builder.add_edge("weather_node", END)
        self._graph_builder.add_edge("search_node", END)
        self._graph_builder.add_edge("generate_itinerary_node", END)

        logger.info("All edges registered in graph")

    def build(self, use_checkpoint: bool = True) -> Any:
        """
        Build and compile the travel planner graph.

        Args:
            use_checkpoint: Whether to enable checkpointing for state persistence.
                           Default is True for production use.

        Returns:
            Compiled LangGraph with optional checkpointing.
        """
        if self._compiled_graph is not None:
            logger.info("Returning cached compiled graph")
            return self._compiled_graph

        self._graph_builder = StateGraph(TravelPlannerState)
        self._add_nodes()
        self._add_edges()

        # Compile with checkpointing if enabled
        if use_checkpoint:
            checkpointer = self.get_checkpointer()
            self._compiled_graph = self._graph_builder.compile(checkpointer=checkpointer)
            logger.info("Compiled graph with checkpointing enabled")
        else:
            self._compiled_graph = self._graph_builder.compile()
            logger.info("Compiled graph without checkpointing")

        # Generate diagram in development only
        try:
            self._compiled_graph.get_graph().draw_mermaid_png(
                output_file_path=r"./logs/travel_routing_3.png"
            )
            logger.info("Generated graph diagram")
        except Exception as e:
            logger.warning("Could not generate graph diagram: %s", e)

        return self._compiled_graph

    async def ainvoke(self, input_state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Async invoke the graph with the given input state.

        Args:
            input_state: The initial state for the graph
            config: Optional configuration including thread_id for checkpointing

        Returns:
            Final state after graph execution
        """
        graph = self.build(use_checkpoint=config.get("configurable", {}).get("thread_id") is not None if config else True)

        try:
            result = await graph.ainvoke(input_state, config=config)
            logger.info("Async invoke completed successfully")
            return result
        except Exception as e:
            logger.error("Error during async invoke: %s", e)
            raise

    def invoke(self, input_state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Sync invoke the graph with the given input state.

        Args:
            input_state: The initial state for the graph
            config: Optional configuration including thread_id for checkpointing

        Returns:
            Final state after graph execution
        """
        graph = self.build(use_checkpoint=config.get("configurable", {}).get("thread_id") is not None if config else True)

        try:
            result = graph.invoke(input_state, config=config)
            logger.info("Invoke completed successfully")
            return result
        except Exception as e:
            logger.error("Error during invoke: %s", e)
            raise

    @classmethod
    def get_graph(cls) -> Optional[Any]:
        """Get the compiled graph if it exists."""
        return cls._compiled_graph

    @classmethod
    def clear_graph(cls) -> None:
        """Clear the compiled graph (useful for testing or hot reload)."""
        cls._compiled_graph = None
        logger.info("Compiled graph cleared")

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
        cls._compiled_graph = None
        cls._checkpointer = None
        logger.info("TravelGraphBuilder singleton reset")
