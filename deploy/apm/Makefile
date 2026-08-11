SHELL := /usr/bin/env bash

COMPOSE := docker compose --project-directory . -f compose.yaml
PYTHON ?= ../../server/.venv/bin/python

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
	RUN_APM_CONTAINER_CONTRACT=1 $(PYTHON) -m pytest -q tests/test_data_plane_contract.py -s
