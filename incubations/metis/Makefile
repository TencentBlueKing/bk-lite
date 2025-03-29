push:
	git add . && codegpt commit . && git push

setup:
	virtualenv .venv -p python3.12
	./.venv/bin/pip install pip-tools

install:
	./.venv/bin/pip-compile ./requirements/requirements-core.txt \
							-v --output-file ./requirements.txt
	./.venv/bin/pip-sync -v
