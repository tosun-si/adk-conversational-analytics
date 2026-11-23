# ADK + Conversational Analytics — chat with your data

2026 FIFA World Cup stats agent (same use case and same BigQuery dataset
`fifa_world_cup_2026` as
`adk-a2ui-copilotkit` / `football-agent-adk-*`), but the ADK agent no longer
writes SQL. It orchestrates the conversation and delegates every data question
to a **Conversational Analytics (CA) data agent**, called as an ADK tool,
either natively or through MCP.

```
ADK agent ──ask_data_agent──► CA data agent ──SQL──► BigQuery
            native: DataAgentToolset
            mcp:    ToolboxToolset → MCP Toolbox for Databases
```

Concepts explained piece by piece: [docs/conversational-analytics.md](docs/conversational-analytics.md).

## Layout

```
data_agent/                 CA data agent as code (no ADK)
  context.py                authored context: schema, synonyms, glossary, verified queries
  system_instruction.yaml   persona + rules with no structured field
  provision.py              create/update (staging / published), delete
  chat.py                   raw stateful chat, prints every stream message
agents/football_ca_agent/   ADK orchestrator
  agent.py                  LlmAgent, one CA toolset + 2 callbacks
  ca_tools.py               CA_MODE=native | mcp
  callbacks.py              pin the data agent, Vega-Lite → PNG artifact
  prompts/                  role + orchestration (no schema, no SQL)
toolbox/tools.yaml          MCP Toolbox: CA ask_data_agent as an MCP tool
scripts/setup_gcp.sh        APIs + IAM
```

## Run

```bash
cp .envrc.example .envrc && direnv allow
gcloud auth application-default login
make setup          # APIs + IAM (once)
make data-agent     # create/update the CA data agent football_world_cup_2026
make ask            # raw CA answer, no ADK
make up             # toolbox :5001, adk web native :8080, adk web MCP :8081
```

Without Docker: `adk web agents` (native), or run the Toolbox binary with
`toolbox --config toolbox/tools.yaml --port 5001` and `CA_MODE=mcp adk web agents`.

Try: "Qui a marqué le plus de buts ?" → "Et pour la France ?" →
"Quel joueur du PSG est le plus décisif ?" (glossary) →
"Compare les buts des 10 meilleurs buteurs en graphique" → "Montre-moi le SQL" →
"Quels sont les xG de Mbappé ?" (the agent says the data does not exist).

The context (instructions, glossary, verified queries) is code in `data_agent/`,
pushed to the data agent only by `make data-agent`: see
[docs/conversational-analytics.md](docs/conversational-analytics.md#where-the-context-lives-and-when-it-is-pushed).
