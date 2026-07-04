from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.langgraph_core.nodes.ai_news_node import AINewsNode
from src.langgraph_core.nodes.chatbot_with_tools_node import AgenticChatbotNode
from src.langgraph_core.nodes.nodes import BasicChatbotNode
from src.langgraph_core.state.states import AINews_State, BasicChatbot
from src.langgraph_core.tools.tools import create_tool_node, get_tools


class BasicChatbotGraphBuilder:
    def __init__(self, model):
        self.llm = model
        self.graph_builder = StateGraph(BasicChatbot)
        self.graph_builder_ainews = StateGraph(AINews_State)

    def basic_chatbot_build_graph(self):
        """
        Builds a basic chatbot graph using LangGraph.
        This method initializes a chatbot node using the `BasicChatbotNode` class
        and integrates it into the graph. The chatbot node is set as both the
        entry and exit point of the graph.
        """
        self.basic_chatbot_node = BasicChatbotNode(self.llm)
        self.graph_builder.add_node("chatbot", self.basic_chatbot_node.chatbot)
        self.graph_builder.add_edge(START, "chatbot")
        self.graph_builder.add_edge("chatbot", END)

    def setup_graph(self):
        self.basic_chatbot_build_graph()
        return self.graph_builder.compile()

    def chatbot_with_tools_build_graph(self):
        """
        Builds an advanced chatbot graph with tool integration.
        This method creates a chatbot graph that includes both a chatbot node
        and a tool node. It defines tools, initializes the chatbot with tool
        capabilities, and sets up conditional and direct edges between nodes.
        The chatbot node is set as the entry point.
        """
        # Define the tool and tool node
        tools = get_tools()
        tool_node = create_tool_node(tools)

        llm = self.llm

        obj_chatbot_with_node = AgenticChatbotNode(llm)
        chatbot_node = obj_chatbot_with_node.create_chatbot(tools)

        # Add nodes
        self.graph_builder.add_node("chatbot", chatbot_node)
        self.graph_builder.add_node("tools", tool_node)
        # Define conditional and direct edges
        self.graph_builder.add_edge(START, "chatbot")
        self.graph_builder.add_conditional_edges("chatbot", tools_condition)
        self.graph_builder.add_edge("tools", "chatbot")

    def setup_agentic_graph(self):
        self.chatbot_with_tools_build_graph()
        return self.graph_builder.compile()

    def ai_news_builder_graph(self):
        ai_news_node = AINewsNode(self.llm)

        # added the nodes

        self.graph_builder_ainews.add_node("fetch_news", ai_news_node.fetch_news)
        self.graph_builder_ainews.add_node("summarize_news", ai_news_node.summarize_news)
        self.graph_builder_ainews.add_node("save_result", ai_news_node.save_result)

        # added the edges

        self.graph_builder_ainews.set_entry_point("fetch_news")
        self.graph_builder_ainews.add_edge("fetch_news", "summarize_news")
        self.graph_builder_ainews.add_edge("summarize_news", "save_result")
        self.graph_builder_ainews.add_edge("save_result", END)

    def setup_ainews_graph(self):
        self.ai_news_builder_graph()
        return self.graph_builder_ainews.compile()
