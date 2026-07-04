from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.langgraph_core.nodes.travel_planner_nodes import TravelPlannerNode
from src.langgraph_core.state.travel_planner_states import TravelPlannerState
from src.langgraph_core.tools.custom_tools import weather_tool
from src.langgraph_core.tools.tools import create_tool_node, get_tools


class TravelGraphBuilder:
    def __init__(self, llm):
        self.llm = llm
        self.graph_builder = StateGraph(TravelPlannerState)
        self.travel_planner_node = TravelPlannerNode(self.llm)

    def _add_nodes(self) -> None:
        """Register all nodes in the graph."""
        self.graph_builder.add_node("router_node", self.travel_planner_node.router)
        self.graph_builder.add_node("chat_node", self.travel_planner_node.chat_node)

        # Tool nodes
        weather_node = ToolNode(tools=[weather_tool])
        self.graph_builder.add_node("weather_node", weather_node)

        tools = get_tools()
        search_node = create_tool_node(tools)
        self.graph_builder.add_node("search_node", search_node)

        # Travel planning nodes
        self.graph_builder.add_node("travel_node", self.travel_planner_node.travel_node)
        self.graph_builder.add_node("collect_missing_travel_info_node", self.travel_planner_node.collect_missing_travel_info)
        self.graph_builder.add_node("process_travel_confirmation_node", self.travel_planner_node.process_travel_confirmation)
        self.graph_builder.add_node("flight_search_node", self.travel_planner_node.flight_search_node)
        self.graph_builder.add_node("flight_selection_node", self.travel_planner_node.flight_selection_node)
        self.graph_builder.add_node("hotel_search_node", self.travel_planner_node.hotel_search_node)
        self.graph_builder.add_node("hotel_selection_node", self.travel_planner_node.hotel_selection_node)
        self.graph_builder.add_node("collect_hotel_info_node", self.travel_planner_node.collect_hotel_info_node)
        self.graph_builder.add_node("generate_itinerary_node", self.travel_planner_node.generate_itinerary_node)

    def _add_edges(self) -> None:
        # Start with router
        self.graph_builder.add_edge(START, "router_node")

        # Router decisions
        self.graph_builder.add_conditional_edges(
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
        self.graph_builder.add_conditional_edges(
            "travel_node",
            lambda state: state.get("route", "chat"),
            {
                "collect_missing_travel_info_node": "collect_missing_travel_info_node",
                "flight_search_node": "flight_search_node",
                "chat": "chat_node",
            },
        )

        # Missing info collection
        self.graph_builder.add_conditional_edges(
            "collect_missing_travel_info_node",
            lambda state: state.get("route", "END"),
            {
                "process_travel_confirmation": "process_travel_confirmation_node",  # After all info collected
                "END": END,
            },
        )

        # Travel confirmation flow
        self.graph_builder.add_conditional_edges(
            "process_travel_confirmation_node",
            lambda state: state.get("route", "END"),
            {
                "flight_search_node": "flight_search_node",  # After user confirms
                "chat_node": "chat_node",  # If user says no
                "END": END,
            },
        )

        # Flight search to selection flow
        self.graph_builder.add_conditional_edges(
            "flight_search_node",
            lambda state: state.get("route", "END"),
            {
                "flight_selection_node": "flight_selection_node",  # After displaying flights
                "hotel_search_node": "hotel_search_node",  # If no flights found
                "END": END,
            },
        )

        self.graph_builder.add_conditional_edges(
            "flight_selection_node",
            lambda state: state.get("route", "END"),
            {
                "hotel_search_node": "hotel_search_node",  # After flight selection
                "END": END,
            },
        )

        # Hotel search to selection flow
        self.graph_builder.add_conditional_edges(
            "hotel_search_node",
            lambda state: state.get("route", "END"),
            {
                "collect_hotel_info_node": "collect_hotel_info_node",
                "hotel_selection_node": "hotel_selection_node",  # After displaying hotels
                "END": END,
            },
        )
        # Hotel info collection flow
        self.graph_builder.add_conditional_edges(
            "collect_hotel_info_node",
            lambda state: state.get("route", "END"),
            {
                "collect_hotel_info_node": "collect_hotel_info_node",  # Self-loop
                "hotel_search_node": "hotel_search_node",  # After all info collected
                "END": END,
            },
        )

        # Hotel selection flow
        self.graph_builder.add_conditional_edges(
            "hotel_selection_node",
            lambda state: state.get("route", "END"),
            {
                "generate_itinerary_node": "generate_itinerary_node",
                "hotel_selection_node": "hotel_selection_node",  # Self-loop for invalid selections
                "END": END,  # Valid selection completes the flow
            },
        )

        # End points
        self.graph_builder.add_edge("chat_node", END)
        self.graph_builder.add_edge("weather_node", END)
        self.graph_builder.add_edge("search_node", END)
        self.graph_builder.add_edge("generate_itinerary_node", END)

    def build(self):
        """Build and compile the travel planner graph."""
        self._add_nodes()
        self._add_edges()
        compiled_graph = self.graph_builder.compile()
        compiled_graph.get_graph().draw_mermaid_png(output_file_path=r"./logs/travel_routing_3.png")
        return compiled_graph
