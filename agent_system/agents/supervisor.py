from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from agent_system.config.settings import get_llm, sanitize_messages
from agent_system.models.state import AgentState, IntentType, RouteTarget


class SupervisorDecision(BaseModel):
    """Structured routing decision produced by the supervisor."""
    reasoning: str = Field(
        description="Brief step-by-step reasoning for why this intent and agent were chosen."
    )
    intent: IntentType = Field(
        description="Classified intent: use_template, explore_sql, data_quality, unknown, or end."
    )
    next_agent: RouteTarget = Field(
        description="Target specialist agent: template_agent, sql_explorer_agent, data_quality_agent, or end."
    )


SUPERVISOR_SYSTEM_PROMPT = """You are the supervisor and router for a FinTech SQL Analytics & Data Quality system.
Your ONLY job is to classify the user's latest message (considering conversation context) and route to the right specialist agent.

## Routing Rules
- use_template -> template_agent: Standard/saved reports like merchant revenue summary, bank failure breakdown, category-wise volume, or listing available saved query templates.
- explore_sql  -> sql_explorer_agent: Ad-hoc or custom analytics questions, filtering by specific city/bank/error code, inspecting database schemas, or saving a newly written query as a template.
- data_quality -> data_quality_agent: Auditing tables for dirty data (duplicates, NULLs, negative test amounts, inconsistent bank/status names) OR cleaning/fixing dirty records (including confirming a cleaning action like "yes, clean it").
- end          -> end: User says goodbye, thanks, done, or exit.
- unknown      -> sql_explorer_agent: Ambiguous request; route here to ask a clarifying question.

## Important Rules
- Do NOT answer the user directly. ONLY classify and route.
- If the user is replying "yes" / "confirm" to a data cleaning confirmation asked by data_quality_agent in the previous turn, ALWAYS route back to data_quality_agent.
- If the user asks a multi-part question, pick the PRIMARY action."""

SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SUPERVISOR_SYSTEM_PROMPT),
    ("placeholder", "{messages}"),
])

_SUPERVISOR_CHAIN = SUPERVISOR_PROMPT | get_llm().with_structured_output(SupervisorDecision)


def supervisor_node(state: AgentState) -> dict:
    """Classifies user intent and decides which specialist agent should run next."""
    decision: SupervisorDecision = _SUPERVISOR_CHAIN.invoke(
        {"messages": sanitize_messages(state["messages"])}
    )
    return {
        "intent": decision.intent,
        "next_agent": decision.next_agent,
    }