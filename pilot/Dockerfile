FROM python:3.10

RUN apt-get update && \
    apt-get install -y libhdf5-dev vim unzip curl pkg-config libssl-dev libffi-dev supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /apps

# ADD ./pyproject.toml ./pyproject.toml
ADD ./requirements ./requirements
RUN pip install -r ./requirements/requirements.in 
RUN pip install -r ./requirements/requirements-dev.in

ADD . .

ADD ./support-files/supervisor/ops-pilot.conf /etc/supervisor/conf.d/ops-pilot.conf
ADD ./support-files/supervisor/ops-pilot-action.conf /etc/supervisor/conf.d/ops-pilot-action.conf
