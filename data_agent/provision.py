"""Create or update the CA data agent from the authored context (idempotent).

A data agent carries two contexts:
  - staging_context   → what you iterate on (chat with context_version=STAGING)
  - published_context → what consumers (ADK, MCP Toolbox, Looker Studio…) get

Default: push the context to BOTH. With --stage-only, only staging is updated,
so you can test it with `python -m data_agent.chat --staging` before publishing.

Usage:
    uv run python -m data_agent.provision [--stage-only] [--delete]
"""

import argparse

from google.api_core import exceptions
from google.cloud import geminidataanalytics_v1 as ca
from google.protobuf import field_mask_pb2

from data_agent.config import (
    DATA_AGENT_ID,
    DATA_AGENT_NAME,
    PARENT,
    ca_client_options,
)
from data_agent.context import build_context

DISPLAY_NAME = "Football World Cup 2026"
DESCRIPTION = (
    "Players, national teams and matches of the 2026 FIFA World Cup "
    "(goals, assists, minutes, cards, clubs, results by stage)."
)


def _data_agent(stage_only: bool) -> ca.DataAgent:
    context = build_context()
    analytics = ca.DataAnalyticsAgent(staging_context=context)
    if not stage_only:
        analytics.published_context = context
    return ca.DataAgent(
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        data_analytics_agent=analytics,
        labels={"use-case": "football", "managed-by": "provision-py"},
    )


def upsert(client: ca.DataAgentServiceClient, stage_only: bool) -> ca.DataAgent:
    agent = _data_agent(stage_only)
    try:
        client.get_data_agent(name=DATA_AGENT_NAME)
    except exceptions.NotFound:
        print(f"Creating {DATA_AGENT_NAME}")
        return client.create_data_agent_sync(
            request=ca.CreateDataAgentRequest(
                parent=PARENT, data_agent_id=DATA_AGENT_ID, data_agent=agent
            )
        )

    agent.name = DATA_AGENT_NAME
    paths = [
        "display_name",
        "description",
        "labels",
        "data_analytics_agent.staging_context",
    ]
    if not stage_only:
        paths.append("data_analytics_agent.published_context")
    print(f"Updating {DATA_AGENT_NAME} ({', '.join(paths)})")
    return client.update_data_agent_sync(
        request=ca.UpdateDataAgentRequest(
            data_agent=agent, update_mask=field_mask_pb2.FieldMask(paths=paths)
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage-only", action="store_true", help="update staging_context only"
    )
    parser.add_argument("--delete", action="store_true", help="delete the data agent")
    args = parser.parse_args()

    client = ca.DataAgentServiceClient(client_options=ca_client_options())
    if args.delete:
        client.delete_data_agent_sync(name=DATA_AGENT_NAME)
        print(f"Deleted {DATA_AGENT_NAME}")
        return

    agent = upsert(client, args.stage_only)
    print(f"OK: {agent.name} (updated {agent.update_time})")


if __name__ == "__main__":
    main()
