\# Hybrid Self-Correcting SQL \& Data Quality Multi-Agent System



!\[Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python\&logoColor=white)

!\[LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C)

!\[LangChain](https://img.shields.io/badge/Framework-LangChain%20Core-green)

!\[Groq](https://img.shields.io/badge/LLM-Groq%20API-orange)

!\[SQLite](https://img.shields.io/badge/Database-SQLite3-003B57?logo=sqlite\&logoColor=white)

!\[Pytest](https://img.shields.io/badge/Tests-8%2F8%20Passing-brightgreen?logo=pytest)



An Agentic AI system built with \*\*LangGraph\*\*, \*\*LangChain Core\*\*, \*\*Groq\*\*, \*\*Pydantic v2\*\*, and \*\*SQLite\*\* that translates natural-language business questions into safe SQL analytics, detects dirty data in real time, self-corrects failed SQL queries, and executes confirmed atomic data-cleaning transactions.



\---



\## Table of Contents



1\. \[Problem Statement \& Why This Architecture?](#1-problem-statement--why-this-architecture)

2\. \[System Architecture](#2-system-architecture)

3\. \[LangGraph Workflow \& Routing](#3-langgraph-workflow--routing)

4\. \[Least-Privilege Tool Access Matrix](#4-least-privilege-tool-access-matrix)

5\. \[End-to-End Request Trace](#5-end-to-end-request-trace)

6\. \[Database Schema \& Injected Dirty Data](#6-database-schema--injected-dirty-data)

7\. \[Repository Structure](#7-repository-structure)

8\. \[Key Engineering \& Security Highlights](#8-key-engineering--security-highlights)

9\. \[Quick Start (Installation \& Setup)](#9-quick-start-installation--setup)

10\. \[Example Queries \& Demo Scenarios](#10-example-queries--demo-scenarios)

11\. \[Automated Testing (`pytest`)](#11-automated-testing-pytest)

12\. \[Known Limitations \& Production Roadmap (v2)](#12-known-limitations--production-roadmap-v2)



\---



\## 1. Problem Statement \& Why This Architecture?



In real-world analytics teams, both existing approaches break down:



\* \*\*Pre-Saved BI Queries / Dashboards\*\* are fast and deterministic, but they cannot answer ad-hoc root-cause questions (combinatorial explosion of filters) and \*\*silently compute wrong metrics\*\* when dirty data enters the database (e.g., webhook retry duplicates doubling `SUM(amount)`).

\* \*\*Standard Text-to-SQL Chatbots\*\* guess table/column names, crash on SQLite syntax errors, and assume categorical columns are clean (missing rows when `'HDFC'`, `'HDFC Bank'`, and `'hdfc\_bank'` coexist).



\### The Hybrid Solution

This project combines both worlds into a \*\*3-Path Multi-Agent Supervisor System\*\*:



| Path | Handled By | Purpose |

| :--- | :--- | :--- |

| \*\*1. Fast Verified Path\*\* | `template\_agent` | Runs pre-saved, verified SQL templates from `saved\_queries.json` for standard reports. |

| \*\*2. Ad-Hoc Self-Correcting Path\*\* | `sql\_explorer\_agent` | Inspects live schemas \& distinct column values, writes dirty-data-aware `SELECT` SQL, self-corrects on DB errors, and saves new templates on request. |

| \*\*3. Data Quality \& Remediation Path\*\* | `data\_quality\_agent` | Audits tables for anomalies (duplicates, NULLs, negative test rows, naming drift) and cleans them inside atomic SQLite transactions after explicit user confirmation. |



> \*\*Core Design Principle:\*\* \*The LLM handles language understanding and planning; pure Python tools enforce SQL security, schema validation, and database invariants.\*



\---



\## 2. System Architecture



The application is strictly separated into \*\*5 decoupled layers\*\*:



```text

┌─────────────────────────────────────────────────────────────────────────────────────┐

│ 1. PRESENTATION LAYER (main.py)                                                     │

│    • Interactive CLI REPL + Token-by-Token Streaming                                │

│    • Whitelist Node Filtering (hides internal Supervisor JSON from end-user)        │

│    • Error State Rollback via history.pop() on API / Recursion errors               │

└──────────────────────────────────────────┬──────────────────────────────────────────┘

&#x20;                                          │

&#x20;                                          ▼

┌─────────────────────────────────────────────────────────────────────────────────────┐

│ 2. ORCHESTRATION LAYER (agent\_system/workflows/graph.py — LangGraph StateGraph)     │

│    • Shared AgentState using built-in `add\_messages` reducer                        │

│    • Pydantic v2 SupervisorDecision (CoT-first: reasoning -> intent -> next\_agent)  │

│    • Conditional routing + recursion\_limit=20 safety guardrail                      │

└──────────────────────────────────────────┬──────────────────────────────────────────┘

&#x20;                                          │

&#x20;        ┌─────────────────────────────────┼─────────────────────────────────┐

&#x20;        ▼                                 ▼                                 ▼

┌─────────────────────────────────────────────────────────────────────────────────────┐

│ 3. REASONING LAYER (agent\_system/agents/ — 3 Specialist ReAct Agents)               │

│                                                                                     │

│  ┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐  │

│  │    template\_agent     │   │  sql\_explorer\_agent   │   │  data\_quality\_agent   │  │

│  │  (Fast Saved Queries) │   │ (Ad-Hoc Self-Correct) │   │ (Audit \& Safe Clean)  │  │

│  │        2 Tools        │   │        4 Tools        │   │        3 Tools        │  │

│  └───────────┬───────────┘   └───────────┬───────────┘   └───────────┬───────────┘  │

│              │ ▲                         │ ▲                         │ ▲            │

│              ▼ │ ReAct                   ▼ │ ReAct                   ▼ │ ReAct      │

│     \[template\_tools]            \[explorer\_tools]            \[quality\_tools]         │

│    (Isolated ToolNode)         (Isolated ToolNode)         (Isolated ToolNode)      │

└──────────────┬───────────────────────────┬───────────────────────────┬──────────────┘

&#x20;              │                           │                           │

&#x20;              ▼                           ▼                           ▼

┌─────────────────────────────────────────────────────────────────────────────────────┐

│ 4. BUSINESS LOGIC \& GUARDRAILS LAYER (agent\_system/tools/ — Pure Python)            │

│    • template\_tools.py : list\_saved\_templates, run\_saved\_template                   │

│    • sql\_tools.py      : list\_tables\_and\_schemas, get\_distinct\_column\_values,       │

│                          execute\_safe\_select\_sql (Regex Guardrail),                 │

│                          save\_new\_query\_template                                    │

│    • quality\_tools.py  : audit\_table\_anomalies, clean\_dirty\_records (ACID Txn)      │

└──────────────────────────────────────────┬──────────────────────────────────────────┘

&#x20;                                          │

&#x20;                                          ▼

┌─────────────────────────────────────────────────────────────────────────────────────┐

│ 5. DATA LAYER (database/ — SQLite3 + JSON Registry)                                 │

│    • fintech\_analytics.db : 20 Merchants, 3,145 UPI Transactions (Indexed)          │

│    • saved\_queries.json   : Verified Pre-Saved SQL Templates                        │

└─────────────────────────────────────────────────────────────────────────────────────┘

```



\---



\## 3. LangGraph Workflow \& Routing



The compiled graph consists of \*\*7 nodes\*\* (1 Supervisor + 3 Specialist Agents + 3 isolated `ToolNode`s), \*\*4 conditional edges\*\*, and \*\*4 fixed edges\*\*:



```mermaid

flowchart TD

&#x20;   START(\[START]) --> SUP\[supervisor<br/>Pydantic Structured Output]



&#x20;   SUP -->|use\_template| TA\[template\_agent]

&#x20;   SUP -->|explore\_sql / unknown| SEA\[sql\_explorer\_agent]

&#x20;   SUP -->|data\_quality| DQA\[data\_quality\_agent]

&#x20;   SUP -->|end| END\_NODE(\[END])



&#x20;   TA -->|has tool\_calls| TT\[template\_tools]

&#x20;   TT --> TA

&#x20;   TA -->|no tool\_calls| END\_NODE



&#x20;   SEA -->|has tool\_calls| ET\[explorer\_tools]

&#x20;   ET --> SEA

&#x20;   SEA -->|no tool\_calls| END\_NODE



&#x20;   DQA -->|has tool\_calls| QT\[quality\_tools]

&#x20;   QT --> DQA

&#x20;   DQA -->|no tool\_calls| END\_NODE

```



\### Supervisor Routing Rules

| Intent | Target Agent | Trigger Examples |

| :--- | :--- | :--- |

| `use\_template` | `template\_agent` | Standard reports (merchant revenue, bank failures, city performance) or listing templates |

| `explore\_sql` | `sql\_explorer\_agent` | Custom filters, ad-hoc analysis, schema inspection, saving a new query template |

| `data\_quality` | `data\_quality\_agent` | Auditing dirty data, fixing anomalies, or confirming a cleaning action (`"yes, clean all"`) |

| `unknown` | `sql\_explorer\_agent` | Ambiguous queries (safe fallback to ask a focused clarifying question) |

| `end` | `END` | `"thanks"`, `"bye"`, `"done"` (terminates in 1 LLM call) |



\---



\## 4. Least-Privilege Tool Access Matrix



Security is enforced at \*\*both\*\* the schema level (`.bind\_tools()`) and execution level (isolated `ToolNode` registries — Defense in Depth). Only `data\_quality\_agent` can mutate the SQLite database:



| Tool Name | `template\_agent` | `sql\_explorer\_agent` | `data\_quality\_agent` | Access Type |

| :--- | :---: | :---: | :---: | :--- |

| `list\_saved\_templates` | ✅ | | | READ (JSON) |

| `run\_saved\_template` | ✅ | | | READ (SQLite) |

| `list\_tables\_and\_schemas` | | ✅ | ✅ | READ (SQLite) |

| `get\_distinct\_column\_values` | | ✅ | | READ (SQLite) |

| `execute\_safe\_select\_sql` | | ✅ | | READ-ONLY (`SELECT` / `WITH`) |

| `save\_new\_query\_template` | | ✅ | | WRITE (JSON Registry Only) |

| `audit\_table\_anomalies` | | | ✅ | READ (SQLite) |

| `clean\_dirty\_records` | | | ✅ | \*\*WRITE (SQLite ACID Txn)\*\* |



\---



\## 5. End-to-End Request Trace



Example Query: `"How many HDFC UPI transactions failed and what is their total amount?"`



1\. \*\*Input (`main.py`):\*\* Appends `HumanMessage` to conversation history and calls `analytics\_graph.stream(..., stream\_mode=\["messages", "values"])`.

2\. \*\*Routing (`supervisor`):\*\* Classifies intent as `explore\_sql` and sets `next\_agent = "sql\_explorer\_agent"`. Its structured JSON output is suppressed from the CLI via `USER\_FACING\_NODES` whitelisting.

3\. \*\*Schema Discovery (`sql\_explorer\_agent` → `explorer\_tools`):\*\* Calls `list\_tables\_and\_schemas` to discover `upi\_transactions` and its exact columns (`txn\_id`, `bank\_name`, `amount`, `txn\_status`, `error\_code`).

4\. \*\*Dirty Data Discovery:\*\* Calls `get\_distinct\_column\_values("upi\_transactions", "bank\_name")` and `get\_distinct\_column\_values("upi\_transactions", "txn\_status")`, discovering inconsistent values (`'HDFC'`, `'HDFC Bank'`, `'hdfc\_bank'`, `'hdfc'` and `'FAILED'`, `'failed'`, `'fail'`).

5\. \*\*Safe SQL Execution \& Self-Correction:\*\* Runs a deduplicated, case-insensitive `SELECT` query through `execute\_safe\_select\_sql`. If SQLite returns a syntax or column error, the tool returns `{"success": False, "error": "SQLite Error: ..."}` instead of crashing—allowing the agent to fix and retry automatically.

6\. \*\*Streamed Final Answer:\*\* Streams the accurate metrics token-by-token to the user and flags the detected naming drift, offering a handoff to the Data Quality Agent.



\---



\## 6. Database Schema \& Injected Dirty Data



Running `python database/seed\_db.py` deterministically (`random.Random(42)`) generates a realistic 100-day FinTech UPI dataset (August–November 2026):



\### Tables \& Indexes (`database/fintech\_analytics.db`)

\* \*\*`merchants` (20 rows):\*\* `merchant\_id` (PK), `merchant\_name`, `category` (8 categories), `city` (6 Indian cities: Mumbai, Bengaluru, Delhi, Pune, Hyderabad, Ahmedabad).

\* \*\*`upi\_transactions` (3,145 rows):\*\* `row\_id` (PK), `txn\_id`, `merchant\_id` (FK), `customer\_vpa`, `bank\_name`, `amount`, `txn\_status`, `error\_code`, `created\_at`.

\* \*\*Indexes:\*\* `idx\_txn\_bank\_status(bank\_name, txn\_status)`, `idx\_txn\_merchant(merchant\_id)`, `idx\_txn\_id(txn\_id)`.



\### Intentionally Injected Anomalies

| Anomaly Type | Count / Rate | Simulated Real-World Cause |

| :--- | :--- | :--- |

| \*\*Duplicate `txn\_id`\*\* | 65 rows | Bank webhook retries inserting the same `txn\_id` 3–10 seconds later |

| \*\*Negative / Zero Amounts\*\* | 35 rows | QA/staging test accounts (`qa\_bot@upi`, `testuser@upi`) with `-500`, `-100`, `-1`, `0` |

| \*\*`NULL` Amounts\*\* | 45 rows | Malformed upstream API payloads missing the amount field |

| \*\*Naming \& Casing Drift\*\* | \~8% banks, \~6% status | Partner APIs sending `'HDFC Bank'`, `'hdfc\_bank'`, `'sbi\_bank'`, `'completed'`, `'done'`, `'fail'` |



\### Pre-Saved Templates (`database/saved\_queries.json`)

1\. `merchant\_revenue\_summary` — Revenue and transaction count by merchant \& city.

2\. `bank\_failure\_breakdown` — Failed transactions and UPI error codes (`U30\_BANK\_TIMEOUT`, `U16\_RISK\_THRESHOLD`, etc.) by bank.

3\. `category\_wise\_volume` — Transaction volume across merchant categories.

4\. `city\_wise\_performance` — Revenue comparison across cities.



\---



\## 7. Repository Structure



```text

sql\_quality\_agent/

├── main.py                              # CLI REPL, whitelist token streaming, history rollback

├── requirements.txt                     # Minimal, clean dependencies

├── .env                                 # API keys \& model config (gitignored)

├── .gitignore                           # UTF-8 gitignore (.env, \*.db, \_\_pycache\_\_, venv)

├── README.md                            # Complete project documentation

├── database/

│   ├── seed\_db.py                       # Deterministic FinTech DB + anomaly generator

│   ├── fintech\_analytics.db             # Generated SQLite database (gitignored)

│   └── saved\_queries.json               # Pre-saved verified SQL templates

├── agent\_system/

│   ├── config/

│   │   └── settings.py                  # Module-level ChatGroq singleton + sanitize\_messages()

│   ├── models/

│   │   └── state.py                     # AgentState TypedDict with add\_messages reducer

│   ├── tools/

│   │   ├── template\_tools.py            # 2 tools for pre-saved query templates

│   │   ├── sql\_tools.py                 # 4 tools for schema exploration \& safe SELECT SQL

│   │   └── quality\_tools.py             # 2 tools for anomaly auditing \& atomic cleaning

│   ├── agents/

│   │   ├── supervisor.py                # Pydantic structured router

│   │   ├── template\_agent.py            # Fast-path template specialist

│   │   ├── sql\_explorer\_agent.py        # Self-correcting SQL specialist

│   │   └── data\_quality\_agent.py        # Audit \& confirmed remediation specialist

│   └── workflows/

│       └── graph.py                     # StateGraph wiring \& conditional routing

└── tests/

&#x20;   └── test\_tools.py                    # 8 zero-LLM pytest unit tests (isolated temp DB)

```



\---



\## 8. Key Engineering \& Security Highlights



\* \*\*Deterministic SQL Guardrails:\*\* `execute\_safe\_select\_sql` blocks all non-`SELECT` statements, multi-statement `;` chains, and DDL/DML keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `PRAGMA`) via regex before SQLite ever sees the query.

\* \*\*SQL Injection Prevention in Schema Tools:\*\* `get\_distinct\_column\_values` validates `table\_name` against `sqlite\_master` and `column\_name` against `PRAGMA table\_info` before querying.

\* \*\*Atomic Cleaning Transactions:\*\* `clean\_dirty\_records` only accepts an allowlist of 5 predefined actions (`remove\_duplicates`, `remove\_negative\_amounts`, `remove\_null\_amounts`, `standardize\_names`, `clean\_all`) executed inside `with sqlite3.connect(DB\_PATH) as conn:` (automatic commit/rollback).

\* \*\*Bounded Context Windows:\*\* Query results are capped at 50 rows, distinct values at 30, and anomaly reports return exact counts + top 5 sample rows to prevent token blowups.

\* \*\*Module-Level LLM Singleton \& Pre-Bound Chains:\*\* `get\_llm()` instantiates `ChatGroq` once at `temperature=0.0`, avoiding per-node client allocation overhead.

\* \*\*Session-Safe Error Recovery:\*\* `main.py` catches `GraphRecursionError` and API exceptions and calls `history.pop()`, preventing consecutive `HumanMessage` state corruption.



\---



\## 9. Quick Start (Installation \& Setup)



\### Prerequisites

\* Python 3.10+

\* A free \[Groq API Key](https://console.groq.com/)



\### Setup Steps



```bash

\# 1. Clone the repository

git clone <your-repo-url>

cd sql\_quality\_agent



\# 2. Create and activate a virtual environment

python -m venv venv

\# Windows (PowerShell):

venv\\Scripts\\activate

\# macOS / Linux:

source venv/bin/activate



\# 3. Install dependencies

pip install -r requirements.txt



\# 4. Create a .env file in the project root

```



Add your credentials to `.env`:



```env

GROQ\_API\_KEY=your\_actual\_groq\_api\_key\_here

MODEL\_NAME=openai/gpt-oss-120b

TEMPERATURE=0.0

```



```bash

\# 5. Seed the SQLite database \& saved query templates

python database/seed\_db.py



\# 6. Launch the interactive CLI agent

python main.py

```



\---



\## 10. Example Queries \& Demo Scenarios



Try running these prompts in sequence to see all 3 agents in action:



1\. \*\*Fast Saved Template (`template\_agent`):\*\*

&#x20;  ```text

&#x20;  Show me the merchant revenue summary

&#x20;  ```

2\. \*\*Ad-Hoc Dirty-Data SQL (`sql\_explorer\_agent`):\*\*

&#x20;  ```text

&#x20;  How many HDFC UPI transactions failed and what is their total amount?

&#x20;  ```

3\. \*\*Save a Custom Query as a Reusable Template (`sql\_explorer\_agent`):\*\*

&#x20;  ```text

&#x20;  Save that query as hdfc\_failed\_summary

&#x20;  ```

4\. \*\*Full Database Health Audit (`data\_quality\_agent`):\*\*

&#x20;  ```text

&#x20;  Audit upi\_transactions for dirty data

&#x20;  ```

5\. \*\*Confirmed Atomic Data Cleanup (`data\_quality\_agent`):\*\*

&#x20;  ```text

&#x20;  Clean all dirty records

&#x20;  ```

&#x20;  \*(The agent will prompt for explicit `yes/no` confirmation before executing the atomic SQLite transaction.)\*

6\. \*\*Re-run Saved Template After Cleanup:\*\*

&#x20;  ```text

&#x20;  Show me the merchant revenue summary

&#x20;  ```

&#x20;  \*(Compare the deduplicated, cleaned revenue figures against Step 1!)\*



\---



\## 11. Automated Testing (`pytest`)



Because business logic and SQL guardrails live in pure Python tools (decoupled from the LLM), \*\*100% of tool validation, security blockers, atomic cleaning, and graph routing logic is unit-tested with zero API calls\*\* using isolated `tmp\_path` SQLite fixtures.



```bash

pip install pytest

python -m pytest -v

```



\*\*Expected Output:\*\*

```text

tests/test\_tools.py::test\_list\_tables\_and\_schemas PASSED                                   \[ 12%]

tests/test\_tools.py::test\_get\_distinct\_column\_values\_valid\_and\_invalid PASSED              \[ 25%]

tests/test\_tools.py::test\_execute\_safe\_select\_blocks\_write\_queries PASSED                  \[ 37%]

tests/test\_tools.py::test\_execute\_safe\_select\_returns\_sqlite\_error\_without\_crashing PASSED \[ 50%]

tests/test\_tools.py::test\_save\_new\_query\_template PASSED                                   \[ 62%]

tests/test\_tools.py::test\_template\_list\_and\_run PASSED                                     \[ 75%]

tests/test\_tools.py::test\_audit\_and\_atomic\_clean\_all PASSED                                \[ 87%]

tests/test\_tools.py::test\_routing\_functions PASSED                                         \[100%]



=================================== 8 passed in \~1.5s ====================================

```



\---



\## 12. Known Limitations \& Production Roadmap (v2)



This system is designed as a single-user local analytics prototype. To deploy in a multi-user production environment, the following upgrades are planned in priority order:



| Priority | Upgrade | Reason |

| :--- | :--- | :--- |

| \*\*P0\*\* | \*\*LangGraph Checkpointer (`SqliteSaver` / `PostgresSaver`) + `interrupt\_before=\["quality\_tools"]`\*\* | Moves confirmation gates from probabilistic prompt instructions to code-level graph interrupts, and enables multi-user persistent sessions via `thread\_id`. |

| \*\*P1\*\* | \*\*PostgreSQL Read-Replica / Staging DB + Role-Based Permissions\*\* | Ensures analytical queries never impact live OLTP workloads and enforces read/write isolation at the database user level. |

| \*\*P1\*\* | \*\*FastAPI + WebSocket Backend \& JWT Auth\*\* | Replaces the CLI loop with a streaming web/Slack API while injecting authenticated user/tenant context outside LLM control. |

| \*\*P2\*\* | \*\*LangSmith Tracing \& Routing Evals\*\* | Adds per-turn token/latency observability and automated nightly eval suites measuring routing accuracy and task completion rate. |

| \*\*P2\*\* | \*\*Mixed-Model Routing\*\* | Routes the lightweight `supervisor` node to a smaller, faster model while reserving larger reasoning models for complex SQL generation. |

