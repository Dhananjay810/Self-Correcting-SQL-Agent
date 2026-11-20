from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import ToolNode
from agent_system.config.settings import get_llm, sanitize_messages
from agent_system.models.state import AgentState
from agent_system.tools.sql_tools import list_tables_and_schemas
from agent_system.tools.quality_tools import audit_table_anomalies, clean_dirty_records

QUALITY_TOOLS = [list_tables_and_schemas, audit_table_anomalies, clean_dirty_records]
quality_tool_node = ToolNode(tools=QUALITY_TOOLS)

QUALITY_SYSTEM_PROMPT = """You are the Data Quality & Remediation Specialist for a FinTech UPI analytics database.
Your ONLY job is to audit tables for data anomalies and safely clean dirty records inside atomic transactions.

## Workflow
1. For any audit or health check request, call `audit_table_anomalies` and present a clear, structured report of:
   - Duplicate `txn_id` entries
   - Negative or zero test amounts
   - NULL amounts
   - Inconsistent `bank_name` and `txn_status` values
2. If the user asks to clean/fix dirty records:
   - FIRST check if the user has already explicitly confirmed the cleaning action in their latest message (e.g., "yes, clean all", "go ahead and remove duplicates").
   - If NOT confirmed yet, clearly list what will be modified/deleted and ask:
     "Are you sure you want to run `<action>` on `upi_transactions`? (yes/no)"
   - Once confirmed, call `clean_dirty_records` with the matching action (`remove_duplicates`, `remove_negative_amounts`, `remove_null_amounts`, `standardize_names`, or `clean_all`).
3. Report the exact row counts updated or removed from the tool response.

## Rules
- NEVER call `clean_dirty_records` without explicit user confirmation first.
- NEVER fabricate audit counts; always run `audit_table_anomalies` for live database state."""

QUALITY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", QUALITY_SYSTEM_PROMPT),
    ("placeholder", "{messages}"),
])

_QUALITY_CHAIN = QUALITY_PROMPT | get_llm().bind_tools(QUALITY_TOOLS)


def data_quality_agent_node(state: AgentState) -> dict:
    """Audits tables for anomalies and performs confirmed atomic data cleaning."""
    response = _QUALITY_CHAIN.invoke({"messages": sanitize_messages(state["messages"])})
    return {
        "messages": [response],
        "final_response": response.content if not response.tool_calls else None,
    }