# `make` with no target prints this list.

QUESTION ?= Qui a marqué le plus de buts ?

.DEFAULT_GOAL := help
.PHONY: help setup sync data-agent data-agent-stage data-agent-delete chat ask up down lint

help:  ## Show this help
	@grep -E '^[a-z][a-z0-9-]*:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup:  ## Enable APIs + grant IAM roles to the current gcloud account
	./scripts/setup_gcp.sh

sync:  ## Install the Python deps (uv)
	uv sync

data-agent:  ## Create/update the CA data agent (staging + published context)
	uv run python -m data_agent.provision

data-agent-stage:  ## Update ONLY the staging context (test it with `make chat ARGS=--staging`)
	uv run python -m data_agent.provision --stage-only

data-agent-delete:  ## Delete the CA data agent
	uv run python -m data_agent.provision --delete

chat:  ## Raw CA chat without ADK, every stream message printed (REPL)
	uv run python -m data_agent.chat $(ARGS)

ask:  ## One-shot raw CA question: make ask QUESTION="..."
	uv run python -m data_agent.chat $(ARGS) "$(QUESTION)"

up:  ## Start toolbox (:5001), adk web native (:8080), adk web MCP (:8081)
	docker compose up --build

down:  ## Stop the local stack
	docker compose down

lint:  ## Ruff
	uv run ruff check . && uv run ruff format --check .
