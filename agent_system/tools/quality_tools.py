import sqlite3
from langchain_core.tools import tool
from agent_system.config.settings import DB_PATH


@tool
def audit_table_anomalies() -> dict:
    """
    Audits the 'upi_transactions' table for data quality issues:
    1. Duplicate txn_id records (caused by webhook retries)
    2. Negative or zero amounts (test rows)
    3. NULL amounts
    4. Inconsistent bank_name and txn_status naming/casing
    Returns a structured report of all detected anomalies.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Duplicate txn_id
            cur.execute("""
                SELECT txn_id, COUNT(*) AS occurrences
                FROM upi_transactions
                GROUP BY txn_id
                HAVING COUNT(*) > 1;
            """)
            duplicates = [dict(r) for r in cur.fetchall()]

            # 2. Negative or zero amounts
            cur.execute("""
                SELECT row_id, txn_id, customer_vpa, bank_name, amount
                FROM upi_transactions
                WHERE amount <= 0;
            """)
            negative_amounts = [dict(r) for r in cur.fetchall()]

            # 3. NULL amounts
            cur.execute("""
                SELECT row_id, txn_id, customer_vpa, bank_name, txn_status
                FROM upi_transactions
                WHERE amount IS NULL;
            """)
            null_amounts = [dict(r) for r in cur.fetchall()]

            # 4. Distinct bank names and statuses to spot casing/naming drift
            cur.execute("SELECT DISTINCT bank_name FROM upi_transactions ORDER BY bank_name;")
            distinct_banks = [r[0] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT txn_status FROM upi_transactions ORDER BY txn_status;")
            distinct_statuses = [r[0] for r in cur.fetchall()]

        return {
            "success": True,
            "table": "upi_transactions",
            "anomalies": {
                "duplicate_txn_ids": {
                    "total_duplicate_groups": len(duplicates),
                    "sample": duplicates[:5],
                },
                "negative_or_zero_amounts": {
                    "total_rows": len(negative_amounts),
                    "sample": negative_amounts[:5],
                },
                "null_amounts": {
                    "total_rows": len(null_amounts),
                    "sample": null_amounts[:5],
                },
                "distinct_bank_names": distinct_banks,
                "distinct_txn_statuses": distinct_statuses,
            },
        }
    except Exception as exc:
        return {"success": False, "error": f"Audit failed: {exc}"}


@tool
def clean_dirty_records(action: str) -> dict:
    """
    Cleans specific data quality issues in 'upi_transactions' inside an atomic SQLite transaction.
    ALWAYS ask the user for explicit confirmation before calling this tool!
    Args:
        action: Must be one of:
            - 'remove_duplicates': Keeps the earliest row_id per txn_id and deletes duplicate retries.
            - 'remove_negative_amounts': Deletes test rows where amount <= 0.
            - 'standardize_names': Normalizes bank_name ('HDFC Bank'/'hdfc_bank' -> 'HDFC', 'sbi_bank' -> 'SBI')
                                   and txn_status ('Success'/'completed' -> 'SUCCESS').
            - 'remove_null_amounts': Deletes rows where amount IS NULL.
            - 'clean_all': Runs all 4 cleaning steps atomically in a single transaction.
    """
    valid_actions = {
        "remove_duplicates",
        "remove_negative_amounts",
        "standardize_names",
        "remove_null_amounts",
        "clean_all",
    }
    act = action.strip().lower()
    if act not in valid_actions:
        return {
            "success": False,
            "error": f"Invalid action '{action}'. Must be one of: {sorted(valid_actions)}",
        }

    summary = {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()

            if act in ("remove_duplicates", "clean_all"):
                cur.execute("""
                    DELETE FROM upi_transactions
                    WHERE row_id NOT IN (
                        SELECT MIN(row_id) FROM upi_transactions GROUP BY txn_id
                    );
                """)
                summary["duplicates_removed"] = cur.rowcount

            if act in ("remove_negative_amounts", "clean_all"):
                cur.execute("DELETE FROM upi_transactions WHERE amount <= 0;")
                summary["negative_rows_removed"] = cur.rowcount

            if act in ("remove_null_amounts", "clean_all"):
                cur.execute("DELETE FROM upi_transactions WHERE amount IS NULL;")
                summary["null_amount_rows_removed"] = cur.rowcount

            if act in ("standardize_names", "clean_all"):
                cur.execute("""
                    UPDATE upi_transactions
                    SET bank_name = CASE
                        WHEN LOWER(bank_name) LIKE '%hdfc%' THEN 'HDFC'
                        WHEN LOWER(bank_name) LIKE '%sbi%' THEN 'SBI'
                        WHEN LOWER(bank_name) LIKE '%icici%' THEN 'ICICI'
                        WHEN LOWER(bank_name) LIKE '%axis%' THEN 'AXIS'
                        ELSE UPPER(TRIM(bank_name))
                    END,
                    txn_status = CASE
                        WHEN LOWER(txn_status) IN ('success', 'completed', 'done') THEN 'SUCCESS'
                        WHEN LOWER(txn_status) IN ('failed', 'fail', 'error') THEN 'FAILED'
                        ELSE UPPER(TRIM(txn_status))
                    END;
                """)
                summary["rows_standardized"] = cur.rowcount

        return {
            "success": True,
            "action": act,
            "changes": summary,
            "message": f"Successfully executed '{act}' inside an atomic transaction.",
        }
    except Exception as exc:
        return {"success": False, "error": f"Cleaning failed and transaction rolled back: {exc}"}