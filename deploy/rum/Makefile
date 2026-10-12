SHELL := /usr/bin/env bash

COMPOSE := docker compose --env-file .env.example --project-directory . -f compose.yaml

.PHONY: up up-all down ps logs validate test build image

up:
	$(COMPOSE) up -d --wait

up-all:
	$(COMPOSE) --profile dataplane up -d --build --wait

down:
	$(COMPOSE) --profile dataplane down

ps:
	$(COMPOSE) --profile dataplane ps

logs:
	$(COMPOSE) --profile dataplane logs -f --tail=200

validate:
	$(COMPOSE) --profile dataplane config --quiet
	$(MAKE) -C collector validate-config
	$(MAKE) -C collector build

test:
	$(MAKE) -C collector test test-controller test-maintainer

build:
	$(MAKE) -C collector build

image:
	$(MAKE) -C collector image
