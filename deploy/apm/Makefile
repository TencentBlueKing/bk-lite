SHELL := /usr/bin/env bash

COMPOSE := docker compose --project-directory . -f compose.yaml
DEMO_COMPOSE := docker compose --project-directory . -f compose.demo.yaml
SERVER_DIR := ../../server

.PHONY: up down ps logs validate test contract demo-up demo-down demo-ps demo-logs demo-seed demo-rollout

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

demo-up: up
	cd $(SERVER_DIR) && uv run python manage.py shell < ../deploy/apm/demo/ensure_application.py
	$(DEMO_COMPOSE) up -d --build --wait
	cd $(SERVER_DIR) && uv run python manage.py shell < ../deploy/apm/demo/seed_control_plane.py

demo-down:
	$(DEMO_COMPOSE) down

demo-ps:
	$(DEMO_COMPOSE) ps

demo-logs:
	$(DEMO_COMPOSE) logs -f --tail=200

demo-seed:
	cd $(SERVER_DIR) && uv run python manage.py shell < ../deploy/apm/demo/seed_control_plane.py

demo-rollout:
	$(DEMO_COMPOSE) up -d --build --force-recreate apm-demo-storefront apm-demo-catalog apm-demo-orders apm-demo-inventory apm-demo-payment
