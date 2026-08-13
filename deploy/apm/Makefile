SHELL := /usr/bin/env bash

COMPOSE := docker compose --project-directory . -f compose.yaml
SERVER_DIR := ../../server

.PHONY: up down ps logs validate test contract

up:
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200

validate:
	$(COMPOSE) config --quiet
	$(MAKE) -C collector validate

test:
	$(MAKE) -C collector test

contract:
	cd $(SERVER_DIR) && RUN_APM_CONTAINER_CONTRACT=1 uv run pytest -q ../deploy/apm/tests/test_data_plane_contract.py -s
