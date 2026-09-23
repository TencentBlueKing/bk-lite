SHELL := /usr/bin/env bash

COMPOSE := docker compose --env-file .env.example --project-directory . -f compose.yaml

.PHONY: up down ps logs validate test build

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
	$(MAKE) -C collector validate-config
	$(MAKE) -C collector build

test:
	$(MAKE) -C collector test test-controller test-maintainer

build:
	$(MAKE) -C collector build
