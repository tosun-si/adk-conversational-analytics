"""Tool callbacks around `ask_data_agent`.

before: pin the data agent (native mode — MCP mode uses Toolbox bound_params).
after:  CA answers with a Vega-Lite chart spec when a chart helps. That spec
        (with its inline data) is large and useless to the LLM, and `adk web`
        cannot render Vega-Lite. We render it to PNG, save it as an ADK
        artifact (shown in the chat) and replace it by a short reference.
"""

import json
import logging
from typing import Any

import vl_convert as vlc
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .ca_tools import ASK_TOOL_NAME, DATA_AGENT_NAME

logger = logging.getLogger(__name__)


def pin_data_agent(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict | None:
    if tool.name == ASK_TOOL_NAME and "data_agent_name" in args:
        # Native DataAgentToolset takes the full resource name from the LLM.
        # Overwrite it: the orchestrator talks to ONE governed data agent.
        args["data_agent_name"] = DATA_AGENT_NAME
    return None


def _vega_spec(message: Any) -> dict | None:
    if not isinstance(message, dict):
        return None
    chart = message.get("chart")
    if not isinstance(chart, dict):
        return None
    result = chart.get("result")
    return result.get("vegaConfig") if isinstance(result, dict) else None


def _mcp_messages(tool_response: Any) -> list | None:
    """Toolbox (MCP) → the tool returns a str (ADK wraps it in {"result": str}
    only AFTER this callback). That str is a JSON-encoded string whose content
    is NDJSON: one CA message per line."""
    text = tool_response
    if isinstance(text, dict):
        text = text.get("result")
    if not isinstance(text, str):
        return None
    try:
        if text.lstrip().startswith('"'):
            text = json.loads(text)
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError:
        return None


async def render_ca_charts(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> dict | None:
    if tool.name != ASK_TOOL_NAME:
        return None

    native = isinstance(tool_response, dict) and isinstance(
        tool_response.get("response"), list
    )
    messages = tool_response["response"] if native else _mcp_messages(tool_response)
    if messages is None:
        return None

    rendered = 0
    for i, message in enumerate(messages):
        spec = _vega_spec(message)
        if not spec:
            continue
        filename = f"chart_{tool_context.function_call_id or 'ca'}_{i}.png"
        try:
            png = vlc.vegalite_to_png(spec, scale=2)
        except Exception:  # a bad spec must not break the answer
            logger.exception("Vega-Lite rendering failed")
            continue
        version = await tool_context.save_artifact(
            filename, types.Part.from_bytes(data=png, mime_type="image/png")
        )
        messages[i] = {
            "chart": f"Chart rendered and shown to the user as artifact "
            f"'{filename}' (v{version}). Do not describe the chart spec."
        }
        rendered += 1

    if not rendered:
        return None
    if native:
        return tool_response
    # Back to NDJSON, single-encoded (also lighter for the LLM than the original).
    return {"result": "\n".join(json.dumps(m, ensure_ascii=False) for m in messages)}
