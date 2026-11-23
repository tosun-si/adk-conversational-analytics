"""The Conversational Analytics tool, two interchangeable transports.

CA_MODE=native (default) — ADK built-in `DataAgentToolset`
    In-process, calls the CA Chat API directly with the agent's credentials.
    No extra server. Recommended by Google for governed data agents in ADK.

CA_MODE=mcp — MCP Toolbox for Databases (`toolbox/tools.yaml`)
    The same CA data agent exposed as an MCP tool by a Toolbox server. The ADK
    agent only knows an MCP URL; the Toolbox holds the GCP identity. Any MCP
    client (Gemini CLI, IDEs, another framework) can reuse the exact same tool.

Both call the SAME data agent → the semantics (context, glossary, verified
queries) live in the data agent, not in the transport. Both are stateless at
the CA level: ADK owns the conversation memory (see prompts/orchestration.md).
"""

import os

import google.auth
from google.adk.tools.data_agent.config import DataAgentToolConfig
from google.adk.tools.data_agent.credentials import DataAgentCredentialsConfig
from google.adk.tools.data_agent.data_agent_toolset import DataAgentToolset
from google.adk.tools.toolbox_toolset import ToolboxToolset

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "gb-poc-373711")
# Must match the data agent created by `data_agent/provision.py`.
CA_LOCATION = os.environ.get("CA_LOCATION", "global")
DATA_AGENT_ID = os.environ.get("CA_DATA_AGENT_ID", "football_world_cup_2026")
DATA_AGENT_NAME = (
    f"projects/{PROJECT_ID}/locations/{CA_LOCATION}/dataAgents/{DATA_AGENT_ID}"
)

CA_MODE = os.environ.get("CA_MODE", "native").lower()
TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5001")
# Rows returned to the LLM (the CA agent itself analyses the full result).
MAX_ROWS = int(os.environ.get("CA_MAX_ROWS", "50"))

ASK_TOOL_NAME = "ask_data_agent"  # same name in both transports


def _native_toolset() -> DataAgentToolset:
    credentials, _ = google.auth.default()
    return DataAgentToolset(
        credentials_config=DataAgentCredentialsConfig(credentials=credentials),
        data_agent_tool_config=DataAgentToolConfig(
            max_query_result_rows=MAX_ROWS,
            location=CA_LOCATION,
            # Read-only: the orchestrator may ask, never create/update agents.
            enable_data_agent_modification=False,
        ),
        # Only the chat tool: listing agents is useless when the agent is
        # pinned, and fewer tools = fewer wrong tool calls.
        tool_filter=[ASK_TOOL_NAME],
    )


def _mcp_toolset() -> ToolboxToolset:
    return ToolboxToolset(
        server_url=TOOLBOX_URL,
        tool_names=[ASK_TOOL_NAME],
        # Bound params are REMOVED from the schema the LLM sees and injected at
        # call time → the model cannot pick (or hallucinate) another agent.
        bound_params={"data_agent_id": DATA_AGENT_ID},
    )


def build_ca_toolset():
    if CA_MODE == "native":
        return _native_toolset()
    if CA_MODE == "mcp":
        return _mcp_toolset()
    raise ValueError(f"CA_MODE must be 'native' or 'mcp', got {CA_MODE!r}")
