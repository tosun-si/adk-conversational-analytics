#!/usr/bin/env bash
# One-time project setup for Conversational Analytics + ADK.
#   ./scripts/setup_gcp.sh [principal]     e.g. user:me@example.com
# Principal defaults to the active gcloud account.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-gb-poc-373711}"
PRINCIPAL="${1:-user:$(gcloud config get-value account 2>/dev/null)}"

echo "▶ Enabling APIs on ${PROJECT_ID}"
gcloud services enable --project "${PROJECT_ID}" \
  geminidataanalytics.googleapis.com \
  cloudaicompanion.googleapis.com \
  bigquery.googleapis.com \
  aiplatform.googleapis.com

# Least privilege per usage:
#   dataAgentCreator        → provision.py creates the agent (becomes its owner)
#   dataAgentUser           → stateful chat (data_agent/chat.py, Conversations)
#   dataAgentStatelessUser  → stateless chat (ADK DataAgentToolset, MCP Toolbox)
#   bigquery.jobUser/dataViewer → CA runs the SQL with the CALLER's identity
echo "▶ Granting roles to ${PRINCIPAL}"
for role in \
  roles/geminidataanalytics.dataAgentCreator \
  roles/geminidataanalytics.dataAgentUser \
  roles/geminidataanalytics.dataAgentStatelessUser \
  roles/bigquery.jobUser \
  roles/bigquery.dataViewer \
  roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="${PRINCIPAL}" --role="${role}" --condition=None --quiet >/dev/null
  echo "  ✓ ${role}"
done
