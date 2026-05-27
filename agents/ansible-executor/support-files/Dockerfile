FROM ubuntu:24.04

ENV NATS_INSTANCE_ID="default"
ENV NATS_SERVERS="nats://nats:4222"
ENV NATS_USERNAME=""
ENV NATS_PASSWORD=""
ENV NATS_PROTOCOL="nats"
ENV NATS_TLS_CA_FILE=""
ENV NATS_CONNECT_TIMEOUT="5"
ENV ANSIBLE_COLLECTIONS_PATH="/opt/collections"

RUN apt-get update && \
    apt-get install -y python3 python3-venv python3-pip supervisor ansible sshpass && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

COPY pyproject.toml /opt/pyproject.toml
COPY main.py /opt/main.py
COPY support-files/startup.sh /opt/startup.sh
COPY support-files/service.conf /etc/supervisor/conf.d/service.conf

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir nats-py==2.10.0 pyyaml==6.0.2 python-dotenv==1.0.0 pywinrm[credssp]==0.5.0 && \
    mkdir -p /opt/collections && \
    /opt/venv/bin/ansible-galaxy collection install ansible.windows -p /opt/collections

RUN chmod +x /opt/startup.sh

ENTRYPOINT ["/bin/bash", "/opt/startup.sh"]
