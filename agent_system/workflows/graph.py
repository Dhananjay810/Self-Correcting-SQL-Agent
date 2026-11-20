from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from agent_system.models.state import AgentState
from agent_system.agents.supervisor import supervisor_node
from agent_system.agents.template_agent import template_agent_node, template_tool_node
from agent_system.agents.sql_explorer_agent import sql_explorer_agent_node, explorer_tool_node
from agent_system.agents.data_quality_agent import data_quality_agent_node, quality_tool_node


def route_from_supervisor(state: AgentState) -> str:
    """Reads supervisor's routing decision with a safe fallback."""
    target = state.get("next_agent", "sql_explorer_agent")
    valid_targets = {
        "template_agent",
        "sql_explorer_agent",
        "data_quality_agent",
        "end",
    }
    return target if target in valid_targets else "sql_explorer_agent"


def _should_continue(state: AgentState) -> str:
    """If the last AI message contains tool_calls, run tools; otherwise END turn."""
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "tools"
    return "end"


def build_graph():
    workflow = StateGraph(AgentState)

    # Register all 7 nodes (1 supervisor + 3 agents + 3 isolated ToolNodes)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("template_agent", template_agent_node)
    workflow.add_node("template_tools", template_tool_node)
    workflow.add_node("sql_explorer_agent", sql_explorer_agent_node)
    workflow.add_node("explorer_tools", explorer_tool_node)
    workflow.add_node("data_quality_agent", data_quality_agent_node)
    workflow.add_node("quality_tools", quality_tool_node)

    # Entry point
    workflow.add_edge(START, "supervisor")

    # Supervisor conditional routing
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "template_agent": "template_agent",
            "sql_explorer_agent": "sql_explorer_agent",
            "data_quality_agent": "data_quality_agent",
            "end": END,
        },
    )

    # Specialist ReAct loops (Agent <-> Isolated ToolNode)
    workflow.add_conditional_edges(
        "template_agent",
        _should_continue,
        {"tools": "template_tools", "end": END},
    )
    workflow.add_edge("template_tools", "template_agent")

    workflow.add_conditional_edges(
        "sql_explorer_agent",
        _should_continue,
        {"tools": "explorer_tools", "end": END},
    )
    workflow.add_edge("explorer_tools", "sql_explorer_agent")

    workflow.add_conditional_edges(
        "data_quality_agent",
        _should_continue,
        {"tools": "quality_tools", "end": END},
    )
    workflow.add_edge("quality_tools", "data_quality_agent")

    return workflow.compile()


analytics_graph = build_graph()