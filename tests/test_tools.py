import json
import sqlite3
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent_system.tools import sql_tools, template_tools, quality_tools
from agent_system.workflows.graph import route_from_supervisor, _should_continue


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """Creates an isolated temporary SQLite DB and saved_queries.json for every test."""
    db_file = tmp_path / "test_fintech.db"
    templates_file = tmp_path / "test_queries.json"

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE merchants (
            merchant_id TEXT PRIMARY KEY,
            merchant_name TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL
        )
    """)
    cur.execute("INSERT INTO merchants VALUES ('M001', 'QuickMart', 'Grocery', 'Mumbai')")

    cur.execute("""
        CREATE TABLE upi_transactions (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            customer_vpa TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            amount REAL,
            txn_status TEXT NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL
        )
    """)
    rows = [
        ("TXN1", "M001", "a@upi", "HDFC", 1000.0, "SUCCESS", None, "2026-10-01 10:00:00"),
        ("TXN1", "M001", "a@upi", "HDFC", 1000.0, "SUCCESS", None, "2026-10-01 10:00:05"),  # duplicate
        ("TXN2", "M001", "b@upi", "hdfc_bank", 500.0, "completed", None, "2026-10-02 10:00:00"),  # dirty naming
        ("TXN3", "M001", "qa@upi", "ICICI", -50.0, "SUCCESS", None, "2026-10-03 10:00:00"),  # negative
        ("TXN4", "M001", "c@upi", "SBI", None, "FAILED", "U30_BANK_TIMEOUT", "2026-10-04 10:00:00"),  # NULL
    ]
    cur.executemany(
        "INSERT INTO upi_transactions (txn_id, merchant_id, customer_vpa, bank_name, amount, txn_status, error_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    templates_data = {
        "total_rows": {
            "description": "Counts all rows in upi_transactions",
            "sql": "SELECT COUNT(*) AS cnt FROM upi_transactions;",
        }
    }
    templates_file.write_text(json.dumps(templates_data), encoding="utf-8")

    # Redirect all tool modules to use the isolated temporary files
    for mod in (sql_tools, template_tools, quality_tools):
        monkeypatch.setattr(mod, "DB_PATH", db_file)
    for mod in (sql_tools, template_tools):
        monkeypatch.setattr(mod, "TEMPLATES_PATH", templates_file)

    return db_file, templates_file


# --- SQL Tools & Security Guardrail Tests ---

def test_list_tables_and_schemas(temp_env):
    res = sql_tools.list_tables_and_schemas.invoke({})
    assert res["success"] is True
    assert "merchants" in res["tables"]
    assert "upi_transactions" in res["tables"]


def test_get_distinct_column_values_valid_and_invalid(temp_env):
    ok = sql_tools.get_distinct_column_values.invoke(
        {"table_name": "upi_transactions", "column_name": "bank_name"}
    )
    assert ok["success"] is True
    assert "hdfc_bank" in ok["distinct_values"]

    bad_table = sql_tools.get_distinct_column_values.invoke(
        {"table_name": "users; DROP TABLE merchants", "column_name": "bank_name"}
    )
    assert bad_table["success"] is False

    bad_col = sql_tools.get_distinct_column_values.invoke(
        {"table_name": "upi_transactions", "column_name": "non_existent_col"}
    )
    assert bad_col["success"] is False


def test_execute_safe_select_blocks_write_queries(temp_env):
    for dangerous_sql in [
        "DELETE FROM upi_transactions;",
        "DROP TABLE merchants;",
        "UPDATE upi_transactions SET amount = 0;",
        "SELECT 1; DROP TABLE merchants;",
    ]:
        res = sql_tools.execute_safe_select_sql.invoke({"sql_query": dangerous_sql})
        assert res["success"] is False


def test_execute_safe_select_returns_sqlite_error_without_crashing(temp_env):
    res = sql_tools.execute_safe_select_sql.invoke(
        {"sql_query": "SELECT unknown_col FROM upi_transactions;"}
    )
    assert res["success"] is False
    assert "SQLite Error" in res["error"]


def test_save_new_query_template(temp_env):
    res = sql_tools.save_new_query_template.invoke({
        "template_name": "failed_txns",
        "description": "Count failed transactions",
        "sql_query": "SELECT COUNT(*) FROM upi_transactions WHERE txn_status = 'FAILED'",
    })
    assert res["success"] is True

    bad = sql_tools.save_new_query_template.invoke({
        "template_name": "evil_query",
        "description": "Drop table",
        "sql_query": "DROP TABLE upi_transactions",
    })
    assert bad["success"] is False


# --- Template Tools Tests ---

def test_template_list_and_run(temp_env):
    listed = template_tools.list_saved_templates.invoke({})
    assert listed["success"] is True
    assert listed["count"] == 1

    ran = template_tools.run_saved_template.invoke({"template_name": "total_rows"})
    assert ran["success"] is True
    assert ran["rows"][0]["cnt"] == 5

    missing = template_tools.run_saved_template.invoke({"template_name": "does_not_exist"})
    assert missing["success"] is False


# --- Data Quality Audit & Atomic Cleaning Tests ---

def test_audit_and_atomic_clean_all(temp_env):
    audit_before = quality_tools.audit_table_anomalies.invoke({})
    assert audit_before["success"] is True
    anomalies = audit_before["anomalies"]
    assert anomalies["duplicate_txn_ids"]["total_duplicate_groups"] == 1
    assert anomalies["negative_or_zero_amounts"]["total_rows"] == 1
    assert anomalies["null_amounts"]["total_rows"] == 1
    assert "hdfc_bank" in anomalies["distinct_bank_names"]

    # Invalid action rejected
    bad_action = quality_tools.clean_dirty_records.invoke({"action": "drop_everything"})
    assert bad_action["success"] is False

    # Atomic clean_all
    cleaned = quality_tools.clean_dirty_records.invoke({"action": "clean_all"})
    assert cleaned["success"] is True
    assert cleaned["changes"]["duplicates_removed"] == 1
    assert cleaned["changes"]["negative_rows_removed"] == 1
    assert cleaned["changes"]["null_amount_rows_removed"] == 1

    # Verify DB is clean after remediation
    audit_after = quality_tools.audit_table_anomalies.invoke({})
    after = audit_after["anomalies"]
    assert after["duplicate_txn_ids"]["total_duplicate_groups"] == 0
    assert after["negative_or_zero_amounts"]["total_rows"] == 0
    assert after["null_amounts"]["total_rows"] == 0
    assert after["distinct_bank_names"] == ["HDFC"]
    assert after["distinct_txn_statuses"] == ["SUCCESS"]


# --- Graph Routing Unit Tests ---

def test_routing_functions():
    assert route_from_supervisor({"next_agent": "template_agent"}) == "template_agent"
    assert route_from_supervisor({"next_agent": "garbage_node"}) == "sql_explorer_agent"

    msg_with_tool = AIMessage(content="", tool_calls=[{"name": "list_tables_and_schemas", "args": {}, "id": "c1"}])
    assert _should_continue({"messages": [msg_with_tool]}) == "tools"
    assert _should_continue({"messages": [AIMessage(content="Done!")]}) == "end"
    assert _should_continue({"messages": [HumanMessage(content="Hi")]}) == "end"