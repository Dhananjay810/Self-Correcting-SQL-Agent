from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import ToolNode
from agent_system.config.settings import get_llm, sanitize_messages
from agent_system.models.state import AgentState
from agent_system.tools.sql_tools import (
    list_tables_and_schemas,
    get_distinct_column_values,
    execute_safe_select_sql,
    save_new_query_template,
)

EXPLORER_TOOLS = [
    list_tables_and_schemas,
    get_distinct_column_values,
    execute_safe_select_sql,
    save_new_query_template,
]
explorer_tool_node = ToolNode(tools=EXPLORER_TOOLS)

EXPLORER_SYSTEM_PROMPT = """You are the Self-Correcting SQL Explorer Specialist for a FinTech UPI analytics database (SQLite).
Your ONLY job is to answer ad-hoc data questions by writing and executing safe, read-only SQLite SELECT queries—and saving verified queries as templates when requested.

## Workflow
1. Always call `list_tables_and_schemas` first to inspect exact table and column names. Never guess schemas.
2. Before filtering on categorical columns (like `bank_name`, `txn_status`, `city`, `category`), call `get_distinct_column_values` to check for dirty/inconsistent values (e.g., 'HDFC' vs 'HDFC Bank' vs 'hdfc_bank', or 'SUCCESS' vs 'completed').
3. Write a clean SQLite SELECT query that handles dirty data accurately:
   - Use `COUNT(DISTINCT txn_id)` when counting transactions to avoid overcounting webhook retry duplicates.
   - Exclude invalid/negative test amounts (`amount > 0`) when summing revenue unless the user specifically asks to include them.
   - Use case-insensitive matching (`LOWER(...)` or `IN (...)`) based on the distinct values you observed.
4. Call `execute_safe_select_sql`. If it returns an error, READ the error carefully, fix the SQL, and retry (self-correct).
5. If the user explicitly asks to save the query for future use, call `save_new_query_template`.

## Rules
- NEVER invent numbers. Every figure in your final response must come directly from `execute_safe_select_sql`.
- Mention the SQL logic briefly and flag any dirty data patterns you noticed (e.g., "Note: I detected inconsistent bank names like 'hdfc_bank' and excluded negative test amounts. Let me know if you want the Data Quality Agent to audit and clean them!").
- If the user's request is ambiguous, ask one focused clarifying question."""

EXPLORER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", EXPLORER_SYSTEM_PROMPT),
    ("placeholder", "{messages}"),
])

_EXPLORER_CHAIN = EXPLORER_PROMPT | get_llm().bind_tools(EXPLORER_TOOLS)


def sql_explorer_agent_node(state: AgentState) -> dict:
    """Explores schemas, detects dirty values, writes & self-corrects SELECT SQL."""
    response = _EXPLORER_CHAIN.invoke({"messages": sanitize_messages(state["messages"])})
    return {
        "messages": [response],
        "final_response": response.content if not response.tool_calls else None,
    }