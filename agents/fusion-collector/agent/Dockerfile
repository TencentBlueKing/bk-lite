FROM telegraf:1.33.3

ENV SERVER_URL ""
ENV SERVER_API_TOKEN ""

RUN apt-get update && \
    apt-get install -y ca-certificates ipmitool vim&& \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/fusion-collectors/
ADD ./mibs /usr/share/snmp/mibs
ADD ./collector-sidecar collector-sidecar
ADD ./sidecar.yml sidecar.yml
ADD ./startup.sh startup.sh

RUN mkdir -p /opt/fusion-collectors/bin
RUN mkdir -p /opt/fusion-collectors/cache
RUN mkdir -p /opt/fusion-collectors/log
RUN mkdir -p /opt/fusion-collectors/generated

ADD ./telegraf ./bin/telegraf
ADD ./nats-executor ./bin/nats-executor

RUN chmod +x /opt/fusion-collectors/startup.sh

ENTRYPOINT [ "/opt/fusion-collectors/startup.sh" ]

