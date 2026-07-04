from src.langgraph_core.state.states import BasicChatbot


class BasicChatbotNode:
    def __init__(self, llm):
        self.llm = llm

    def chatbot(self, state: BasicChatbot) -> dict:
        """
        Processes the input state and generates a chatbot response.
        """
        return {"messages": self.llm.invoke(state["messages"])}
