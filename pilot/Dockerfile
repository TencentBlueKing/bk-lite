FROM python:3.10

RUN apt-get update && \
    apt-get install -y libhdf5-dev vim unzip curl pkg-config libssl-dev libffi-dev supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /apps

ADD ./pyproject.toml ./pyproject.toml
RUN pip install pip-tools
RUN pip-compile --extra dev -v
RUN pip install -r requirements.txt

ADD ./actions ./actions
ADD ./channels ./channels
ADD ./compoments ./compoments
ADD ./libs ./libs
ADD ./utils ./utils
ADD ./cli.py ./cli.py
ADD ./core ./core
ADD ./custom_broker ./custom_broker
ADD ./eventbus ./eventbus
ADD ./support-files/supervisor/ops-pilot.conf /etc/supervisor/conf.d/ops-pilot.conf
ADD ./support-files/supervisor/ops-pilot-action.conf /etc/supervisor/conf.d/ops-pilot-action.conf
