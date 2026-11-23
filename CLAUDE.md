# CLAUDE.md — adk-conversational-analytics

2026 World Cup stats agent. ADK is the orchestrator; a **Conversational
Analytics (CA) data agent** answers every data question (NL → SQL → BigQuery →
analysis → Vega-Lite chart). Basis of an article + video on CA. Sibling repos:
`adk-a2ui-copilotkit` (BigQuery MCP agent writing its own SQL, A2UI frontend).

Concepts and how they map to the code: `docs/conversational-analytics.md`.

## Key rules

- **Semantics live in the data agent, not in the ADK prompt.** Schema, synonyms,
  glossary, verified queries → `data_agent/context.py` + `system_instruction.yaml`.
  The ADK prompts must not mention columns or SQL.
- **`make data-agent` after any context change** (the agent is a remote
  resource). Iterate with `make data-agent-stage` + `make chat ARGS=--staging`.
- **CA tools are stateless** (ADK and MCP): the orchestrator rewrites follow-ups
  into self-contained questions (`prompts/orchestration.md` rule 3).
- **Data agent is pinned**, never chosen by the LLM: `before_tool_callback`
  (native) / Toolbox `bound_params` (mcp).
- **Charts**: CA v1 returns only Vega-Lite specs. `callbacks.render_ca_charts`
  renders them to PNG artifacts (vl-convert) and strips the spec from what the
  LLM sees.
- **`CA_LOCATION=global`**: MCP Toolbox always calls the global CA endpoint.
- **Tool response shapes differ**: native → `{"status", "response": [msg]}`;
  Toolbox → a JSON-encoded **str of NDJSON** (one CA message per line), seen
  raw by `after_tool_callback` (ADK wraps it in `{"result"}` only after).
- **Toolbox host port 5001** (macOS AirPlay owns 5000); Toolbox 1.x serves
  `/mcp` only (`/api/*` → 410).
- **Data**: the 5 tables of `fifa_world_cup_2026` (built by the sibling repo
  `adk-a2ui-copilotkit/data/`). Names: display `player_name`, filter
  `player_search_name` LIKE. No shots / xG: the context says so. Encoded in
  the context, never in the ADK prompts.
- Data agent: `football_world_cup_2026`. The former `football_qatar_2022` was
  deleted on 2026-11-23 (soft delete: its id is reserved until the 30-day purge).
- The agent package does not import `data_agent/` (keeps `adk web agents`
  working without PYTHONPATH); IDs are duplicated via env vars
  (`CA_LOCATION`, `CA_DATA_AGENT_ID`).

## Stack / versions

- google-adk >= 2.14 (`DataAgentToolset` since 1.23), `[toolbox]` extra; google-genai 2.x (ADK pins < 3)
- google-cloud-geminidataanalytics >= 0.13.6 (`geminidataanalytics_v1`, GA)
- MCP Toolbox image `toolbox:1.13.1` (`--config`, `--address 0.0.0.0`)
- GCP project `gb-poc-373711`, dataset `fifa_world_cup_2026` (europe-west1)
- Orchestrator model `gemini-3.8-flash`, `MODEL_LOCATION=global` (2.5 retired 2026-10-20)

## Conventions

- Personal open-source repo → descriptive commit titles, no Co-Authored-By,
  HEREDOC for multi-line bodies.
- `make` lists commands; Docker (`make up`) is the canonical local path.
