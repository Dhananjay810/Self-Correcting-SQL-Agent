from typing import Annotated, List, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

IntentType = Literal["use_template", "explore_sql", "data_quality", "unknown", "end"]
RouteTarget = Literal["template_agent", "sql_explorer_agent", "data_quality_agent", "end"]


class AgentState(TypedDict):
    """Shared state passed across all nodes in the LangGraph workflow."""
    messages: Annotated[List[BaseMessage], add_messages]
    intent: Optional[IntentType]
    next_agent: Optional[RouteTarget]
    final_response: Optional[str]