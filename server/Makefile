push:
	git add . && codegpt commit . && git push

install:
	uv sync --all-groups
	uv sync --all-extras

shell:
	uv run python manage.py shell_plus
	
migrate:
	uv run python manage.py makemigrations
	uv run python manage.py migrate
	uv run python manage.py createcachetable django_cache

server-init:
	uv run python manage.py init_realm_resource
	uv run python manage.py init_login_settings
	uv run python manage.py create_user admin password --email=admin@bklite.net --is_superuser
	uv run python manage.py model_init
	uv run python manage.py plugin_init
	uv run python manage.py node_init
	uv run python manage.py log_init
	uv run python manage.py init_bot
	uv run python manage.py init_channel
	uv run python manage.py init_llm
	uv run python manage.py create_builtin_rules --update

setup-dev-user:
	DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=admin@example.com DJANGO_SUPERUSER_PASSWORD=password uv run python manage.py createsuperuser --noinput

i18n:
	uv run python manage.py makemessages -l zh_Hans
	uv run python manage.py makemessages -l en
	uv run python manage.py compilemessages

collect-static:
	uv run python manage.py collectstatic --noinput

dev:
	uv run uvicorn asgi:application --host 0.0.0.0 --port 8001 --reload --workers 1

clean-migrate:
	cd apps &&\
	find . -path "*/migrations/*.py" -not -name "__init__.py" -delete &&\
	find . -path "*/migrations/*.pyc"  -delete

init-buckets:
	python manage.py initialize_buckets

celery:
	uv run celery -A apps.core.celery worker -B --loglevel=info --pool threads

celery-inspect:
	uv run celery -A apps.core.celery inspect scheduled

start-nats:
	uv run python manage.py nats_listener

test:
	uv run pytest
