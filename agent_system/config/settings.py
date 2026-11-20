import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage

load_dotenv()

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "database" / "fintech_analytics.db"
TEMPLATES_PATH = BASE_DIR / "database" / "saved_queries.json"

# LLM Settings (Groq API)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing! Please set it in your .env file.")

# Module-level Singleton LLM instance
_llm_instance = None


def get_llm() -> ChatGroq:
    """Returns a singleton instance of the Groq LLM."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatGroq(
            groq_api_key=GROQ_API_KEY,
            model_name=MODEL_NAME,
            temperature=TEMPERATURE,
        )
    return _llm_instance


def sanitize_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Replaces empty/null content with a single space during tool calling
    while preserving tool_calls and tool_call_id pairing.
    """
    sanitized = []
    for msg in messages:
        content = msg.content
        is_empty = content is None or content == "" or content == []
        if is_empty:
            if isinstance(msg, AIMessage):
                sanitized.append(
                    AIMessage(
                        content=" ",
                        tool_calls=getattr(msg, "tool_calls", []),
                        id=getattr(msg, "id", None),
                    )
                )
            elif isinstance(msg, ToolMessage):
                sanitized.append(
                    ToolMessage(
                        content=" ",
                        tool_call_id=getattr(msg, "tool_call_id", ""),
                        id=getattr(msg, "id", None),
                    )
                )
            else:
                sanitized.append(msg)
        else:
            sanitized.append(msg)
    return sanitized