"""Shared settings for the Conversational Analytics (CA) data agent."""

import os

from google.api_core import client_options

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "gb-poc-373711")
# Location of the CA *data agent* resource (not of the BigQuery dataset).
# `global` is the default of both ADK and MCP Toolbox; the Toolbox CA tools
# always call the global endpoint, so keep `global` unless you only use the
# native ADK path (which also supports `eu` / `us` / regional endpoints).
CA_LOCATION = os.environ.get("CA_LOCATION", "global")
DATA_AGENT_ID = os.environ.get("CA_DATA_AGENT_ID", "football_world_cup_2026")

# World Cup 2026 dataset (europe-west1), built and loaded by the sibling repo
# adk-a2ui-copilotkit (data/build_dataset.py + data/load_bigquery.sh).
DATASET_ID = "fifa_world_cup_2026"

PARENT = f"projects/{PROJECT_ID}/locations/{CA_LOCATION}"
DATA_AGENT_NAME = f"{PARENT}/dataAgents/{DATA_AGENT_ID}"


def fq(table: str) -> str:
    """Fully qualified BigQuery table name (used in the verified queries)."""
    return f"{PROJECT_ID}.{DATASET_ID}.{table}"


def ca_client_options(location: str = CA_LOCATION) -> client_options.ClientOptions:
    """Endpoint routing for the CA API (same rules as the official SDK guide)."""
    if not location or location == "global":
        endpoint = "geminidataanalytics.googleapis.com"
    elif "-" in location:  # regional, e.g. europe-west1
        endpoint = f"geminidataanalytics-{location}.googleapis.com"
    else:  # multi-region with data residency: eu, us
        endpoint = f"geminidataanalytics.{location}.rep.googleapis.com"
    return client_options.ClientOptions(api_endpoint=endpoint)
