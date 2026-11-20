import json
import sqlite3
from langchain_core.tools import tool
from agent_system.config.settings import DB_PATH, TEMPLATES_PATH


def _load_templates() -> dict:
    if not TEMPLATES_PATH.exists():
        return {}
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@tool
def list_saved_templates() -> dict:
    """
    Lists all pre-saved, verified SQL query templates available in the registry.
    Use this first to check if a user's question can be answered by an existing template.
    """
    try:
        templates = _load_templates()
        summary = [
            {"template_name": name, "description": info.get("description", "")}
            for name, info in templates.items()
        ]
        return {"success": True, "count": len(summary), "templates": summary}
    except Exception as exc:
        return {"success": False, "error": f"Failed to load templates: {exc}"}


@tool
def run_saved_template(template_name: str) -> dict:
    """
    Executes a verified pre-saved SQL query template by its exact name.
    Args:
        template_name: Exact key name from list_saved_templates (e.g., 'merchant_revenue_summary').
    """
    try:
        templates = _load_templates()
        key = template_name.strip()
        if key not in templates:
            return {
                "success": False,
                "error": f"Template '{key}' not found. Available templates: {list(templates.keys())}",
            }

        sql = templates[key]["sql"]
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql)
            rows = [dict(row) for row in cur.fetchmany(50)]

        return {
            "success": True,
            "template_name": key,
            "row_count": len(rows),
            "rows": rows,
        }
    except Exception as exc:
        return {"success": False, "error": f"Error executing template '{template_name}': {exc}"}