"""Raw CA stream viewer — talk to the data agent WITHOUT ADK.

Shows every message type the Chat API streams back, which the ADK tool
flattens: THOUGHT / PROGRESS text, generated SQL, the BigQuery job, the data
result, the matched verified query, the Vega-Lite chart and the final answer.

Stateful by default: a CA `Conversation` is created and Google keeps the
history, so follow-ups ("et pour l'Argentine ?") work without resending it.

Usage:
    uv run python -m data_agent.chat                      # interactive REPL
    uv run python -m data_agent.chat "Top 5 buteurs"      # one shot
    uv run python -m data_agent.chat --staging "..."      # test staging_context
    uv run python -m data_agent.chat --fast "..."         # thinking_mode=FAST
"""

import argparse
import json
import uuid
from pathlib import Path

import vl_convert as vlc
from google.cloud import geminidataanalytics_v1 as ca

from data_agent.config import DATA_AGENT_NAME, PARENT, ca_client_options

OUT_DIR = Path("out")
_COLORS = {"THOUGHT": "\033[90m", "PROGRESS": "\033[36m", "FINAL_RESPONSE": "\033[1m"}
_RESET = "\033[0m"


def _print(tag: str, body: str, color: str = "") -> None:
    print(f"{color}[{tag}] {body}{_RESET}")


def _handle(message: dict, turn: int) -> None:
    sm = message.get("system_message") or {}
    if text := sm.get("text"):
        kind = text.get("text_type", "TEXT")
        _print(kind, "\n".join(text.get("parts", [])), _COLORS.get(kind, ""))
    elif data := sm.get("data"):
        if sql := data.get("generated_sql"):
            _print("SQL", sql, "\033[33m")
        if matched := data.get("matched_query"):
            question = matched.get("example_query", {}).get("natural_language_question")
            _print("VERIFIED QUERY", f"matched: {question!r}", "\033[32m")
        if job := data.get("big_query_job"):
            _print("BQ JOB", job.get("job_id", ""), "\033[90m")
        if result := data.get("result"):
            rows = result.get("data", [])
            _print("DATA", f"{len(rows)} rows")
            for row in rows[:10]:
                print("   ", json.dumps(row, ensure_ascii=False))
    elif chart := sm.get("chart"):
        spec = (chart.get("result") or {}).get("vega_config")
        if spec:
            OUT_DIR.mkdir(exist_ok=True)
            base = OUT_DIR / f"chart_turn{turn}"
            base.with_suffix(".vl.json").write_text(json.dumps(spec, indent=2))
            base.with_suffix(".png").write_bytes(vlc.vegalite_to_png(spec, scale=2))
            _print("CHART", f"Vega-Lite → {base}.png", "\033[35m")
        elif query := chart.get("query"):
            _print("CHART", f"planning: {query.get('instructions', '')}", "\033[35m")
    elif error := sm.get("error"):
        _print("ERROR", error.get("text", str(error)), "\033[31m")
    elif sm:
        _print(next(iter(sm)).upper(), "(not rendered)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw Conversational Analytics chat")
    parser.add_argument(
        "question", nargs="?", help="one-shot question (REPL if omitted)"
    )
    parser.add_argument("--staging", action="store_true", help="use staging_context")
    parser.add_argument("--fast", action="store_true", help="thinking_mode=FAST")
    args = parser.parse_args()

    client = ca.DataChatServiceClient(client_options=ca_client_options())

    # Stateful chat: the Conversation resource holds the history server-side.
    conversation = client.create_conversation(
        request=ca.CreateConversationRequest(
            parent=PARENT,
            conversation_id=f"cli-{uuid.uuid4().hex[:12]}",
            conversation=ca.Conversation(agents=[DATA_AGENT_NAME]),
        )
    )
    print(f"Conversation: {conversation.name}\n")

    ref = ca.ConversationReference(
        conversation=conversation.name,
        data_agent_context=ca.DataAgentContext(
            data_agent=DATA_AGENT_NAME,
            context_version="STAGING" if args.staging else "PUBLISHED",
        ),
    )

    turn = 0
    question = args.question
    while True:
        if question is None:
            try:
                question = input("\n❓ ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question:
                break
        turn += 1
        request = ca.ChatRequest(
            parent=PARENT,
            messages=[ca.Message(user_message=ca.UserMessage(text=question))],
            conversation_reference=ref,
            thinking_mode="FAST" if args.fast else "THINKING",
        )
        for response in client.chat(request=request, timeout=300):
            _handle(ca.Message.to_dict(response, use_integers_for_enums=False), turn)
        if args.question:
            break
        question = None


if __name__ == "__main__":
    main()
