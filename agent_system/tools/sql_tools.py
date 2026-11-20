import json
import re
import sqlite3
from langchain_core.tools import tool
from agent_system.config.settings import DB_PATH, TEMPLATES_PATH

FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|ATTACH|DETACH|PRAGMA)\b",
    re.IGNORECASE,
)


def _is_safe_select(sql: str) -> tuple[bool, str]:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False, "SQL query is empty."
    if ";" in cleaned:
        return False, "Multiple SQL statements are not allowed."
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        return False, "Only read-only SELECT (or WITH ... SELECT) queries are permitted."
    if FORBIDDEN_SQL_PATTERN.search(cleaned):
        return False, "Forbidden write/DDL keyword detected. Only read-only queries are allowed."
    return True, cleaned


@tool
def list_tables_and_schemas() -> dict:
    """
    Returns all tables in the SQLite database along with their column names and data types.
    Always call this before writing an ad-hoc SQL query or when a table/column error occurs.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cur.fetchall()]

            schema_info = {}
            for table in tables:
                cur.execute(f"PRAGMA table_info({table});")
                cols = [{"name": col[1], "type": col[2], "not_null": bool(col[3])} for col in cur.fetchall()]
                schema_info[table] = cols

        return {"success": True, "tables": schema_info}
    except Exception as exc:
        return {"success": False, "error": f"Failed to inspect schema: {exc}"}


@tool
def get_distinct_column_values(table_name: str, column_name: str) -> dict:
    """
    Fetches up to 30 distinct values for a specific column in a table.
    Use this before filtering on categorical columns (like bank_name, txn_status, city)
    to detect inconsistent casing or dirty naming (e.g., 'HDFC' vs 'hdfc_bank').
    Args:
        table_name: Exact table name (e.g., 'upi_transactions').
        column_name: Exact column name (e.g., 'bank_name').
    """
    try:
        t_name = table_name.strip()
        c_name = column_name.strip()

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            # Validate table name against sqlite_master (prevents SQL injection)
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (t_name,))
            if not cur.fetchone():
                return {"success": False, "error": f"Table '{t_name}' does not exist."}

            # Validate column name against PRAGMA table_info
            cur.execute(f"PRAGMA table_info({t_name});")
            valid_cols = {row[1] for row in cur.fetchall()}
            if c_name not in valid_cols:
                return {
                    "success": False,
                    "error": f"Column '{c_name}' not found in '{t_name}'. Valid columns: {sorted(valid_cols)}",
                }

            cur.execute(f"SELECT DISTINCT {c_name} FROM {t_name} LIMIT 30;")
            values = [row[0] for row in cur.fetchall()]

        return {"success": True, "table": t_name, "column": c_name, "distinct_values": values}
    except Exception as exc:
        return {"success": False, "error": f"Error fetching distinct values: {exc}"}


@tool
def execute_safe_select_sql(sql_query: str) -> dict:
    """
    Executes a read-only SQLite SELECT query and returns up to 50 rows.
    If the query fails (e.g., wrong column or syntax error), the exact SQLite error is returned
    so you can self-correct and retry.
    Args:
        sql_query: Valid SQLite SELECT statement.
    """
    is_valid, result_or_err = _is_safe_select(sql_query)
    if not is_valid:
        return {"success": False, "error": result_or_err}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(result_or_err)
            rows = [dict(row) for row in cur.fetchmany(50)]

        return {
            "success": True,
            "executed_sql": result_or_err,
            "row_count": len(rows),
            "rows": rows,
        }
    except sqlite3.Error as db_err:
        return {
            "success": False,
            "executed_sql": result_or_err,
            "error": f"SQLite Error: {db_err}. Check table/column names using list_tables_and_schemas and retry.",
        }
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error: {exc}"}


@tool
def save_new_query_template(template_name: str, description: str, sql_query: str) -> dict:
    """
    Saves a verified, working SELECT SQL query into saved_queries.json for future reuse.
    Only call this when the user explicitly asks to save a query as a template.
    Args:
        template_name: Short snake_case name (e.g., 'hdfc_timeout_failures').
        description: Brief explanation of what the query calculates.
        sql_query: Verified read-only SELECT SQL query.
    """
    is_valid, cleaned_sql = _is_safe_select(sql_query)
    if not is_valid:
        return {"success": False, "error": f"Cannot save unsafe query: {cleaned_sql}"}

    try:
        templates = {}
        if TEMPLATES_PATH.exists():
            with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
                templates = json.load(f)

        key = template_name.strip().lower().replace(" ", "_")
        templates[key] = {"description": description.strip(), "sql": cleaned_sql}

        with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2)

        return {"success": True, "message": f"Saved query template '{key}' successfully."}
    except Exception as exc:
        return {"success": False, "error": f"Failed to save template: {exc}"}