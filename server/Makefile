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
	uv run python manage.py batch_init

system-init:
	uv run python manage.py parse_tools_yml

setup-dev-user:
	DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=admin@example.com DJANGO_SUPERUSER_PASSWORD=password uv run python manage.py createsuperuser --noinput

i18n:
	uv run python manage.py makemessages -l zh_Hans
	uv run python manage.py makemessages -l en
	uv run python manage.py compilemessages

collect-static:
	uv run python manage.py collectstatic --noinput

dev:
	uv run uvicorn asgi:application --host 0.0.0.0 --port 8011 --reload --workers 1

clean-migrate:
	cd apps &&\
	find . -path "*/migrations/*.py" -not -name "__init__.py" -delete &&\
	find . -path "*/migrations/*.pyc"  -delete

init-buckets:
	python manage.py initialize_buckets

celery:
	uv run celery -A apps.core.celery worker --loglevel=info --pool threads

celery-beat:
	uv run celery -A apps.core.celery beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

celery-inspect:
	uv run celery -A apps.core.celery inspect scheduled

start-nats:
	uv run python manage.py nats_listener

test:
	uv run pytest

# 只跑某个 app：make test-app APP=cmdb
test-app:
	uv run pytest apps/$(APP)/tests

# 按 marker 过滤
test-unit:
	uv run pytest -m unit

test-bdd:
	uv run pytest -m bdd

# CI 快速通道：跳过慢用例
test-fast:
	uv run pytest -m "not slow"

# 调试：关掉覆盖率统计，输出更干净；可叠加路径 make test-debug APP=cmdb
test-debug:
	uv run pytest apps/$(APP)/tests --no-cov

# 改了 migration 后重建测试库
test-reset:
	uv run pytest --create-db

# 启动一次性 PostgreSQL 测试库(Docker),供本地跑 DB 相关用例
# 注意: SQLite 因历史 migration 的全表重建语义无法从零构建,测试库须用 PostgreSQL
TEST_DB_PORT ?= 55432
test-db-up:
	docker rm -f bklite-testdb 2>/dev/null || true
	docker run -d --name bklite-testdb \
		-e POSTGRES_PASSWORD=testpass -e POSTGRES_USER=postgres -e POSTGRES_DB=bklite \
		-p $(TEST_DB_PORT):5432 postgres:15
	@echo "等待 PostgreSQL 就绪..."
	@until docker exec bklite-testdb pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	@echo "测试库已就绪: localhost:$(TEST_DB_PORT)"

test-db-down:
	docker rm -f bklite-testdb 2>/dev/null || true

# 连到测试库跑全部用例(先 make test-db-up)
test-db:
	DB_ENGINE=postgresql DB_NAME=bklite DB_USER=postgres DB_PASSWORD=testpass \
		DB_HOST=localhost DB_PORT=$(TEST_DB_PORT) uv run pytest
