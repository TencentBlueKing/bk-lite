VENV := ./.venv
PIP := $(VENV)/bin/pip
PIP_COMPILE := $(VENV)/bin/pip-compile

PIP_SYNC := $(VENV)/bin/pip-sync

.PHONY: setup clean install-%

setup:
	virtualenv $(VENV) -p python3.12
	$(PIP) install pip-tools

install: 
	$(PIP_COMPILE) ./requirements/requirements.in ./requirements/requirements-dev.in -v --output-file ./requirements.txt
	$(PIP_SYNC) -v
