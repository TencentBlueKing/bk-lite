.PHONY: init validate pull up ps check logs down

init:
	cp -n env.example .env || true

validate:
	docker compose --env-file .env config --quiet

pull:
	docker compose --env-file .env pull

up:
	docker compose --env-file .env up -d

ps:
	docker compose --env-file .env ps

check:
	curl --fail --silent --show-error http://127.0.0.1:$${CONDUCTOR_PORT:-8091}/health

logs:
	docker compose --env-file .env logs -f conductor

down:
	docker compose --env-file .env down
