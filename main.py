from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from agent_system.workflows.graph import analytics_graph

USER_FACING_NODES = {
    "template_agent",
    "sql_explorer_agent",
    "data_quality_agent",
}

BANNER = """
=================================================================
  FinTech SQL Analytics & Data Quality Multi-Agent System
  Powered by LangGraph + Groq (Llama 3.3 70B) + SQLite
=================================================================
Try asking:
  1. Show me the merchant revenue summary (Fast Saved Template)
  2. How many HDFC UPI transactions failed and what was their total amount? (Ad-Hoc Dirty-Data SQL)
  3. Audit the upi_transactions table for dirty data (Data Quality Audit)
  4. Clean all dirty records in upi_transactions (Confirmed Atomic Clean)

Type 'quit' or 'exit' to stop.
-----------------------------------------------------------------
"""


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def main():
    print(BANNER)
    history = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "bye"}:
            print("Agent: Goodbye! Have a great day.")
            break

        history.append(HumanMessage(content=user_input))
        final_messages = None
        printed_prefix = False

        try:
            for event_type, data in analytics_graph.stream(
                {"messages": history},
                stream_mode=["messages", "values"],
                config={"recursion_limit": 20},
            ):
                if event_type == "messages":
                    chunk, meta = data
                    node_name = meta.get("langgraph_node", "")

                    # Only stream tokens from whitelisted user-facing specialist agents
                    if node_name not in USER_FACING_NODES:
                        continue

                    text = _extract_text(chunk.content)
                    if text:
                        if not printed_prefix:
                            print(f"\nAgent ({node_name}): ", end="", flush=True)
                            printed_prefix = True
                        print(text, end="", flush=True)

                elif event_type == "values":
                    final_messages = data.get("messages", history)

            if printed_prefix:
                print()  # newline after streamed response
            elif final_messages and len(final_messages) == len(history):
                print("\nAgent: Glad I could help! Let me know if you need anything else.")

            if final_messages is not None:
                history = final_messages

        except GraphRecursionError:
            print("\nError: The agent reached the maximum reasoning steps. Please rephrase your query simply.")
            history.pop()
        except Exception as exc:
            print(f"\nError: {exc}")
            history.pop()


if __name__ == "__main__":
    main()