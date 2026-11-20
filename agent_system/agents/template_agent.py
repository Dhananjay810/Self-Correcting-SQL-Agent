from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import ToolNode
from agent_system.config.settings import get_llm, sanitize_messages
from agent_system.models.state import AgentState
from agent_system.tools.template_tools import list_saved_templates, run_saved_template

TEMPLATE_TOOLS = [list_saved_templates, run_saved_template]
template_tool_node = ToolNode(tools=TEMPLATE_TOOLS)

TEMPLATE_SYSTEM_PROMPT = """You are the Verified Query Template Specialist for a FinTech analytics system.
Your ONLY job is to answer standard business metric questions using pre-saved, verified SQL templates.

## Workflow
1. Call `list_saved_templates` to check what verified templates exist.
2. If a matching template exists, call `run_saved_template` with its exact `template_name`.
3. Present the results clearly in a clean table or bulleted summary.

## Rules
- NEVER invent numbers or fabricate results. Only report data returned by tools.
- If NO saved template matches the user's specific question, politely tell them which saved templates exist and let them know they can ask it as a custom ad-hoc query."""

TEMPLATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", TEMPLATE_SYSTEM_PROMPT),
    ("placeholder", "{messages}"),
])

_TEMPLATE_CHAIN = TEMPLATE_PROMPT | get_llm().bind_tools(TEMPLATE_TOOLS)


def template_agent_node(state: AgentState) -> dict:
    """Handles fast-path execution of pre-saved SQL templates."""
    response = _TEMPLATE_CHAIN.invoke({"messages": sanitize_messages(state["messages"])})
    return {
        "messages": [response],
        "final_response": response.content if not response.tool_calls else None,
    }