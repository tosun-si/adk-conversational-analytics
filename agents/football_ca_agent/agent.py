"""ADK orchestrator that delegates every data question to a CA data agent.

Split of responsibilities (vs the sibling BigQuery MCP agent, which writes SQL
itself from a schema prompt):

- ADK agent (this file): conversation, intent, follow-up rewriting, tone. It
  knows NOTHING about the table schema and never writes SQL.
- CA data agent (`data_agent/`): NL → SQL → BigQuery → analysis → chart,
  driven by the authored context (glossary, verified queries, …).
"""

import os
from pathlib import Path

from google.adk.agents import LlmAgent

from .ca_tools import CA_MODE, DATA_AGENT_NAME, build_ca_toolset
from .callbacks import pin_data_agent, render_ca_charts

# Same knobs as the sibling repos: gemini-3.x flash is only served from the
# `global` endpoint → MODEL_LOCATION=global routes ONLY the model calls there.
MODEL = os.environ.get("MODEL", "gemini-3.8-flash")
MODEL_LOCATION = os.environ.get("MODEL_LOCATION", "global")

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _instruction() -> str:
    parts = [
        (PROMPTS_DIR / name).read_text() for name in ("role.md", "orchestration.md")
    ]
    return "\n\n".join(parts).replace("{{DATA_AGENT_NAME}}", DATA_AGENT_NAME)


def _model():
    if not MODEL_LOCATION:
        return MODEL
    from google.adk.models import Gemini

    return Gemini(model=MODEL, client_kwargs={"location": MODEL_LOCATION})


root_agent = LlmAgent(
    model=_model(),
    name="football_ca_agent",
    description=(
        "Chats about the 2026 FIFA World Cup statistics. Data questions "
        f"are answered by a Conversational Analytics data agent ({CA_MODE} tool)."
    ),
    instruction=_instruction(),
    tools=[build_ca_toolset()],
    before_tool_callback=pin_data_agent,
    after_tool_callback=render_ca_charts,
)
