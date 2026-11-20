import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "fintech_analytics.db"
TEMPLATES_PATH = DB_DIR / "saved_queries.json"

TOTAL_BASE_TXNS = 3000  # Base transactions (plus ~150 injected anomalies)


def create_and_seed_db():
    if DB_PATH.exists():
        DB_PATH.unlink()

    rng = random.Random(42)  # Deterministic seed for reproducible data
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Merchants Table (20 Merchants across 6 major Indian cities)
    cur.execute("""
        CREATE TABLE merchants (
            merchant_id TEXT PRIMARY KEY,
            merchant_name TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL
        )
    """)

    merchants_data = [
        ("M001", "QuickMart Grocery", "Grocery", "Mumbai"),
        ("M002", "UrbanBites Food", "Food & Dining", "Bengaluru"),
        ("M003", "ElectroHub Store", "Electronics", "Mumbai"),
        ("M004", "MetroFuel Station", "Fuel", "Delhi"),
        ("M005", "FreshBasket Mart", "Grocery", "Pune"),
        ("M006", "SpiceRoute Kitchen", "Food & Dining", "Hyderabad"),
        ("M007", "GadgetZone India", "Electronics", "Bengaluru"),
        ("M008", "CityCare Pharmacy", "Healthcare", "Ahmedabad"),
        ("M009", "StyleStreet Apparel", "Apparel", "Delhi"),
        ("M010", "HighwayFuel Express", "Fuel", "Ahmedabad"),
        ("M011", "DailyNeeds Superstore", "Grocery", "Hyderabad"),
        ("M012", "CafeBrew Roasters", "Food & Dining", "Mumbai"),
        ("M013", "MedPlus Diagnostics", "Healthcare", "Bengaluru"),
        ("M014", "CineMax Multiplex", "Entertainment", "Pune"),
        ("M015", "TechWorld Laptops", "Electronics", "Delhi"),
        ("M016", "TrendWear Studio", "Apparel", "Mumbai"),
        ("M017", "SwiftTravel Cabs", "Travel", "Bengaluru"),
        ("M018", "GreenLeaf Organics", "Grocery", "Ahmedabad"),
        ("M019", "BiryaniHouse Express", "Food & Dining", "Hyderabad"),
        ("M020", "SkyLine Flights", "Travel", "Delhi"),
    ]
    cur.executemany("INSERT INTO merchants VALUES (?, ?, ?, ?)", merchants_data)

    # 2. UPI Transactions Table
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
            created_at TEXT NOT NULL,
            FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id)
        )
    """)

    # Indexes for fast analytical queries on 3,000+ rows
    cur.execute("CREATE INDEX idx_txn_bank_status ON upi_transactions(bank_name, txn_status);")
    cur.execute("CREATE INDEX idx_txn_merchant ON upi_transactions(merchant_id);")
    cur.execute("CREATE INDEX idx_txn_id ON upi_transactions(txn_id);")

    merchant_ids = [m[0] for m in merchants_data]
    customer_names = [
        "rahul", "priya", "amit", "neha", "vikram", "karan", "sneha", "rohit",
        "pooja", "ankit", "divya", "arjun", "meera", "siddharth", "ananya",
        "varun", "kavya", "nikhil", "shreya", "manish", "ritika", "deepak",
    ]
    vpa_handles = ["@okhdfcbank", "@oksbi", "@okicici", "@okaxis", "@ybl", "@ibl"]
    error_codes = [
        "U30_BANK_TIMEOUT",
        "U16_RISK_THRESHOLD",
        "U28_PSP_UNAVAILABLE",
        "ZM_INVALID_MPIN",
        "U09_INSUFFICIENT_FUNDS",
    ]

    # Bank naming variations (clean + dirty)
    clean_banks = ["HDFC", "SBI", "ICICI", "AXIS", "KOTAK"]
    dirty_bank_variants = {
        "HDFC": ["HDFC Bank", "hdfc_bank", "hdfc"],
        "SBI": ["sbi_bank", "SBI Bank", "sbi"],
        "ICICI": ["icici_bank", "ICICI Bank"],
        "AXIS": ["Axis Bank", "axis_bank"],
    }

    start_date = datetime(2026, 8, 1, 8, 0, 0)
    transactions_data = []

    # Generate 3,000 base transactions
    for i in range(1, TOTAL_BASE_TXNS + 1):
        txn_id = f"TXN{10000 + i}"
        merchant_id = rng.choice(merchant_ids)
        vpa = f"{rng.choice(customer_names)}{rng.randint(1, 999)}{rng.choice(vpa_handles)}"
        base_bank = rng.choices(clean_banks, weights=[30, 28, 20, 14, 8])[0]

        # Inject ~8% inconsistent bank names
        if base_bank in dirty_bank_variants and rng.random() < 0.08:
            bank_name = rng.choice(dirty_bank_variants[base_bank])
        else:
            bank_name = base_bank

        # Realistic amount distribution by category feel
        amount = round(rng.uniform(50.0, 18500.0), 2)

        # ~82% SUCCESS, ~18% FAILED (with ~6% inconsistent status casing)
        if rng.random() < 0.82:
            txn_status = rng.choice(["Success", "completed", "done"]) if rng.random() < 0.06 else "SUCCESS"
            error_code = None
        else:
            txn_status = rng.choice(["failed", "fail"]) if rng.random() < 0.06 else "FAILED"
            error_code = rng.choices(error_codes, weights=[40, 20, 15, 10, 15])[0]

        # Random timestamp across 100 days
        offset_seconds = rng.randint(0, 100 * 24 * 3600)
        created_at = (start_date + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")

        transactions_data.append(
            (txn_id, merchant_id, vpa, bank_name, amount, txn_status, error_code, created_at)
        )

    # ANOMALY A: 65 Webhook Retry Duplicates (same txn_id, +3 to +10 seconds later)
    duplicate_samples = rng.sample(transactions_data, 65)
    for row in duplicate_samples:
        orig_dt = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
        retry_dt = (orig_dt + timedelta(seconds=rng.randint(3, 10))).strftime("%Y-%m-%d %H:%M:%S")
        transactions_data.append(
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6], retry_dt)
        )

    # ANOMALY B: 35 Negative / Zero QA Test Amounts left in DB
    for j in range(1, 36):
        txn_id = f"TXN99{j:03d}"
        merchant_id = rng.choice(merchant_ids)
        vpa = rng.choice(["qa_bot@upi", "testuser@upi", "staging_pay@upi"])
        bank_name = rng.choice(["HDFC", "ICICI", "SBI"])
        amount = rng.choice([-500.0, -100.0, -1.0, 0.0])
        created_at = (start_date + timedelta(days=rng.randint(0, 95))).strftime("%Y-%m-%d %H:%M:%S")
        transactions_data.append(
            (txn_id, merchant_id, vpa, bank_name, amount, "SUCCESS", None, created_at)
        )

    # ANOMALY C: 45 NULL Amount records
    for k in range(1, 46):
        txn_id = f"TXN88{k:03d}"
        merchant_id = rng.choice(merchant_ids)
        vpa = f"{rng.choice(customer_names)}{rng.randint(10, 99)}{rng.choice(vpa_handles)}"
        bank_name = rng.choice(["HDFC", "SBI", "AXIS", "ICICI"])
        status = rng.choice(["SUCCESS", "FAILED"])
        err = None if status == "SUCCESS" else "U30_BANK_TIMEOUT"
        created_at = (start_date + timedelta(days=rng.randint(0, 95))).strftime("%Y-%m-%d %H:%M:%S")
        transactions_data.append(
            (txn_id, merchant_id, vpa, bank_name, None, status, err, created_at)
        )

    cur.executemany("""
        INSERT INTO upi_transactions
        (txn_id, merchant_id, customer_vpa, bank_name, amount, txn_status, error_code, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, transactions_data)

    conn.commit()
    conn.close()
    print(f"[OK] SQLite Database created at: {DB_PATH}")
    print(f"     Merchants: {len(merchants_data)} | Total Transactions: {len(transactions_data)}")
    print("     Injected Anomalies: 65 duplicates, 35 negative/zero rows, 45 NULL amounts, ~8% naming drift")


def create_saved_templates():
    templates = {
        "merchant_revenue_summary": {
            "description": "Calculates total successful revenue and transaction count grouped by merchant name and city.",
            "sql": """
                SELECT m.merchant_name, m.city, COUNT(DISTINCT t.txn_id) AS total_txns, ROUND(SUM(t.amount), 2) AS total_revenue
                FROM upi_transactions t
                JOIN merchants m ON t.merchant_id = m.merchant_id
                WHERE UPPER(t.txn_status) IN ('SUCCESS', 'COMPLETED', 'DONE') AND t.amount > 0
                GROUP BY m.merchant_name, m.city
                ORDER BY total_revenue DESC;
            """
        },
        "bank_failure_breakdown": {
            "description": "Shows failed transaction count and failure error codes grouped by bank.",
            "sql": """
                SELECT UPPER(bank_name) AS bank, error_code, COUNT(DISTINCT txn_id) AS failed_count
                FROM upi_transactions
                WHERE UPPER(txn_status) IN ('FAILED', 'FAIL')
                GROUP BY UPPER(bank_name), error_code
                ORDER BY failed_count DESC;
            """
        },
        "category_wise_volume": {
            "description": "Shows total transaction volume across different merchant categories (Grocery, Electronics, Travel, etc.).",
            "sql": """
                SELECT m.category, COUNT(DISTINCT t.txn_id) AS txn_count, ROUND(SUM(t.amount), 2) AS volume
                FROM upi_transactions t
                JOIN merchants m ON t.merchant_id = m.merchant_id
                WHERE t.amount > 0
                GROUP BY m.category
                ORDER BY volume DESC;
            """
        },
        "city_wise_performance": {
            "description": "Compares total transactions and total successful revenue across cities.",
            "sql": """
                SELECT m.city, COUNT(DISTINCT t.txn_id) AS total_txns, ROUND(SUM(t.amount), 2) AS total_revenue
                FROM upi_transactions t
                JOIN merchants m ON t.merchant_id = m.merchant_id
                WHERE UPPER(t.txn_status) IN ('SUCCESS', 'COMPLETED', 'DONE') AND t.amount > 0
                GROUP BY m.city
                ORDER BY total_revenue DESC;
            """
        }
    }

    with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2)
    print(f"[OK] Saved Query Templates created at: {TEMPLATES_PATH} ({len(templates)} verified templates)")


if __name__ == "__main__":
    create_and_seed_db()
    create_saved_templates()