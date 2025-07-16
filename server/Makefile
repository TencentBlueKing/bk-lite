push:
	git add . && codegpt commit . && git push

setup:
	virtualenv .venv -p python3.10
	./.venv/bin/pip install pip-tools

compile:
	./.venv/bin/pip-compile ./requirements/requirements-core.txt \
							./requirements/requirements-cmdb.txt \
							./requirements/requirements-console.txt \
							./requirements/requirements-monitor.txt \
							./requirements/requirements-node_mgmt.txt \
							./requirements/requirements-opspilot.txt \
							./requirements/requirements-system_mgmt.txt \
							./requirements/requirements-mlops.txt \
							-v --output-file ./requirements.txt

install:
	./.venv/bin/pip-sync -v

win-install:
	.\.venv\Scripts\pip-compile.exe ./requirements/requirements-core.txt ./requirements/requirements-dev.txt ./requirements/requirements-ops.txt  ./requirements/requirements-extra.txt -v --output-file ./requirements.txt
	.\.venv\Scripts\pip-sync.exe -v

migrate:
	python manage.py makemigrations
	python manage.py migrate
	python manage.py createcachetable django_cache

server-init:
	python manage.py init_realm_resource
	python manage.py init_login_settings 
	python manage.py create_user admin password --email=admin@bklite.net --is_superuser 
	python manage.py model_init
	python manage.py plugin_init 
	python manage.py node_init
	python manage.py init_bot 
	python manage.py init_channel 
	python manage.py init_llm 
	python manage.py create_builtin_rules --update

setup-dev-user:
	DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=admin@example.com DJANGO_SUPERUSER_PASSWORD=password python manage.py createsuperuser --noinput

i18n:
	python manage.py makemessages -l zh_Hans
	python manage.py makemessages -l en
	python manage.py compilemessages

collect-static:
	python manage.py collectstatic --noinput

dev:
	python ./manage.py runserver 0.0.0.0:8001

run:
	gunicorn -w 4 -b 0.0.0.0:8001 asgi:application -k uvicorn.workers.UvicornWorker

clean-migrate:
	cd apps &&\
	find . -path "*/migrations/*.py" -not -name "__init__.py" -delete &&\
	find . -path "*/migrations/*.pyc"  -delete

init-buckets:
	python manage.py initialize_buckets

celery:
	celery -A apps.core.celery worker -B --loglevel=info --pool threads

celery-inspect:
	celery -A apps.core.celery inspect scheduled

celery-flower:
	celery -A apps.core.celery flower

start-nats:
	python manage.py nats_listener

build-system-manager:
	docker build -f ./support-files/release/system-manager/Dockerfile -t bklite/system-manager .

build-console:
	docker build -f ./support-files/release/console/Dockerfile -t bklite/ops-console .

build-node-manager:
	docker build -f ./support-files/release/node-manager/Dockerfile -t bklite/node-manager .

build-cmdb:
	docker build -f ./support-files/release/cmdb/Dockerfile -t bklite/cmdb .

build-monitor:
	docker build -f ./support-files/release/monitor/Dockerfile -t bklite/monitor .

build-opspilot:
	docker build -f ./support-files/release/opspilot/Dockerfile -t bklite/ops-pilot .

test:
	pytest
