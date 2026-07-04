from typing import Annotated

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import Any, Dict, List, TypedDict


class BasicChatbot(TypedDict):
    """A basic chatbot with a simple conversation flow."""

    messages: Annotated[List, add_messages]


class AINews_State(TypedDict):
    """
    Represent the structure of the state used in graph
    """

    messages: Annotated[List, add_messages]
    # derived state variables through pipeline
    frequency: str  # "daily" | "weekly" | "monthly" | "year"
    news_data: List[Dict[str, Any]]  # results from Tavily
    summary: str  # markdown-formatted summary
    filename: str


class Blog(BaseModel):
    title: str = Field(description="the title of the blog post")
    content: str = Field(description="The main content of the blog post")


class BlogState(TypedDict):
    topic: str
    blog: Blog
    current_language: str
