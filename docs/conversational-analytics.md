# Conversational Analytics, piece by piece

How each Conversational Analytics (CA) concept maps to this repo.

```
User ──► ADK agent (football_ca_agent)          orchestrator: dialogue, intent, rewriting
            │  ask_data_agent(query)             one tool, two transports:
            │    CA_MODE=native → DataAgentToolset (in-process, REST)
            │    CA_MODE=mcp    → ToolboxToolset → MCP Toolbox → REST
            ▼
        CA Chat API  (geminidataanalytics.googleapis.com, v1 GA)
            │  DataAgentContext → data agent "football_world_cup_2026"
            ▼
        Data agent = datasource + authored context (published / staging)
            │  NL → SQL → BigQuery job (caller identity) → rows → analysis → chart
            ▼
        BigQuery  gb-poc-373711.fifa_world_cup_2026.{players, teams, team_matches,
                                                    player_matches, matches}
```

## 1. Two services

| Service | Resource | Used by |
|---|---|---|
| `DataAgentService` | `DataAgent` (create / update / IAM) | `data_agent/provision.py` |
| `DataChatService` | `Conversation`, `Message`, `chat` | `data_agent/chat.py`, ADK tool, Toolbox |

## 2. The data agent

A persistent, IAM-governed resource
(`projects/{p}/locations/{loc}/dataAgents/{id}`) that bundles:

- **Datasource references**: here the 5 BigQuery tables of `fifa_world_cup_2026`. (Also: Looker explores,
  Looker Studio, AlloyDB/Cloud SQL/Spanner in preview.)
- **Authored context**: everything in `data_agent/context.py`.
- **Options**: `big_query_max_billed_bytes` (cost guardrail, 1 GB here).

It is written once and consumed everywhere: ADK, MCP Toolbox, raw API, and the
BigQuery / Looker Studio consoles. That reuse is the point of a data agent
compared to `ask_data_insights` (the schema-only `BigQueryToolset` tool).

### Staging vs published context

`DataAnalyticsAgent` has `staging_context` and `published_context`. Chat
requests pick one with `DataAgentContext.context_version`. There is no
"publish" RPC: publishing = updating `published_context`.

```bash
make data-agent-stage                 # push to staging only
make chat ARGS=--staging              # try it
make data-agent                       # publish (staging + published)
```

## 3. Authored context (the semantic layer)

Accuracy comes from here, not from the orchestrator prompt. Priority order
(Google's guidance): structured fields first, `system_instruction` for the rest.

| Element | Where | Why |
|---|---|---|
| Table description, synonyms, tags | `Schema` × 5 in `_TABLES` | Table selection (`players` first for player questions) |
| Column description, synonyms | `Field` (only where FR vocabulary helps; the rest comes from the BigQuery column descriptions) | FR words → EN columns (`buts` → `goals`, `titularisations` → `matches_started`) |
| Glossary terms | `GlossaryTerm` × 9 in `_GLOSSARY` | Business vocabulary: "joueur décisif", "phase finale", "champion du monde", "joueur de Ligue 1", "PSG" |
| Example queries | `ExampleQuery` × 8 (two parameterized `{player}`) | Used as **verified queries**; the stream returns `matched_query` when one is reused |
| System instruction (YAML) | `system_instruction.yaml` | Persona, default aggregations, joins, accent-free names, FR → EN team names, no xG / shots |

Console names (BigQuery → Agents → the agent → edit): **Instructions** =
`system_instruction`, **Glossary** = `glossary_terms`, **Verified queries** =
`example_queries`, table/field metadata = `datasource_references`.

### Where the context lives and when it is pushed

Nothing is configured by hand in the console. The context is code
(`context.py` + `system_instruction.yaml`), assembled by `build_context()` and
sent by `provision.py` with `CreateDataAgent` (first run) or `UpdateDataAgent`
(update mask on `staging_context` / `published_context`). It is pushed **only
when you run** `make data-agent` (or `make data-agent-stage`): never at ADK
start-up, never per question. The ADK agent and the Toolbox only send the data
agent *name*; CA loads the published context server-side on each chat call.
A console edit is overwritten by the next `make data-agent`.

The sibling agent (`adk-a2ui-copilotkit`) needs all of this in its LLM prompt (`schema.md`,
`query_workflow.md`, `business_rules.md`). Here it moved into the data agent;
the ADK prompt no longer contains a single column name.

## 4. Chat modes

| Mode | How | Where in this repo |
|---|---|---|
| Stateful, Google-managed history | `Conversation` + `ConversationReference` | `data_agent/chat.py` (follow-ups work natively) |
| Stateless, agent reference | `ChatRequest.data_agent_context` | ADK `DataAgentToolset`, MCP Toolbox |
| Stateless, inline context | `ChatRequest.inline_context` (no data agent) | not used; that is what `ask_data_insights` does |

The ADK tools are stateless → ADK owns the memory, and the orchestrator must
send self-contained questions (rule 3 of `prompts/orchestration.md`: "Et pour
l'Argentine ?" → "Top 3 buteurs de l'Argentine"). The Toolbox tool parameter is
even named `user_query_with_context`.

`thinking_mode`: `THINKING` (default) or `FAST` (lower latency,
`make chat ARGS=--fast`). `Deep dive` exists in preview (allowlist).

## 5. The response stream

`chat` streams `Message`s; each `system_message` is one of:

| Message | Content | ADK tool output |
|---|---|---|
| `text` / `THOUGHT` | reasoning steps | kept |
| `text` / `PROGRESS` | status ("Retrieved context for 1 table") | kept |
| `data.generated_sql` | the SQL | `generatedSql` |
| `data.big_query_job` | job id (labelled `ca-bq-job`) | kept |
| `data.result` | rows + schema | `Data Retrieved` (capped at `CA_MAX_ROWS`, only the last result) |
| `data.matched_query` | verified query that was reused | kept |
| `chart.result.vega_config` | **Vega-Lite spec** (PNG/SVG removed in v1) | rendered to PNG by `callbacks.render_ca_charts` |
| `text` / `FINAL_RESPONSE` | the answer | kept |
| `error` | failure | kept |

`make ask QUESTION="..."` prints every one of them, colour-coded; charts land
in `out/`.

## 6. Native tool vs MCP tool

| | `CA_MODE=native` | `CA_MODE=mcp` |
|---|---|---|
| Class | `google.adk.tools.data_agent.DataAgentToolset` | `google.adk.tools.toolbox_toolset.ToolboxToolset` |
| Extra process | none | MCP Toolbox server (`toolbox/tools.yaml`) |
| GCP identity | the ADK agent's ADC / SA | the Toolbox's (or forwarded user OAuth with `useClientOAuth`) |
| Data agent pinning | `before_tool_callback` overwrites `data_agent_name` | `bound_params={"data_agent_id": ...}` (hidden from the LLM) |
| Locations | global, `eu`/`us`, regional | global (Toolbox calls the global endpoint) |
| Reuse by other clients | ADK only | any MCP client (Gemini CLI, IDEs, …) |

Both call the same REST `…:chat` with the same data agent and flatten the
stream the same way (ADK's `_gda_stream_util` is a port of the Toolbox code).

Recommendation: `native` inside an ADK app (one process fewer, one identity);
`mcp` when the same governed tool must be shared with non-ADK clients.

## 7. IAM

CA runs BigQuery jobs with the **caller's** identity: row/column security and
dataset ACLs still apply.

| Role | For |
|---|---|
| `geminidataanalytics.dataAgentCreator` | create agents (creator becomes owner) |
| `geminidataanalytics.dataAgentUser` | stateful chat on a shared agent |
| `geminidataanalytics.dataAgentStatelessUser` | stateless chat (ADK / Toolbox) |
| `bigquery.jobUser` + `bigquery.dataViewer` | run the generated SQL |

## 8. Not used yet (next steps)

- **A2A (preview since 2026-06)**: CA data agents expose `GetAgentCard` /
  `SendMessage` → an ADK `RemoteA2aAgent` could talk to the data agent directly.
- **Agent observability (2026-09)**: latency / token metrics per data agent,
  Cloud Trace integration.
- **Custom streaming sub-agent**: stream THOUGHT/PROGRESS to the UI live
  (the built-in tools buffer the whole stream).
- **Frontend**: render the Vega-Lite spec natively in CopilotKit (vega-embed)
  instead of a PNG.
