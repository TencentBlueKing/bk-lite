FROM ubuntu:24.04

ENV SERVER_URL ""
ENV SERVER_API_TOKEN ""
ENV SIDECAR_ZONE "default"
ENV SIDECAR_GROUP "default"
ENV SIDECAR_NODEID ""
ENV SIDECAR_NODENAME "telegraf-proxy"

RUN apt-get update && \
    apt-get install -y ca-certificates ipmitool vim snmp supervisor zip iputils-ping snmptrapd openjdk-11-jdk sshpass && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/fusion-collectors/

# Sidecar 
ADD ./collector-sidecar collector-sidecar
ADD ./sidecar.yml sidecar.yml
ADD ./startup.sh startup.sh
ADD ./snmptrap-to-socket ./bin/snmptrap-to-socket
ADD ./misc misc

# sidecar 从工作目录读 VERSION 返回版本信息；与发布 zip 包一致，
# 从 misc/VERSION（版本真源）派生纯版本号文件
RUN . /opt/fusion-collectors/misc/VERSION && \
    echo "${LINUX_SIDECAR_VERSION}" > /opt/fusion-collectors/VERSION

RUN bash -c "mkdir -p /opt/fusion-collectors/{bin,cache,log,generated} /opt/release && \
    chmod +x /opt/fusion-collectors/startup.sh /opt/fusion-collectors/bin/snmptrap-to-socket"

# Telegraf
ADD ./mibs /usr/share/snmp/mibs
ADD ./telegraf ./bin/telegraf

# NatsExecutor
ADD ./nats-executor ./bin/nats-executor

# Vector
ADD ./vector ./bin/vector

ADD ./filebeat ./bin/filebeat
ADD ./packetbeat ./bin/packetbeat
ADD ./auditbeat ./bin/auditbeat
ADD ./windows /opt/release/windows/fusion-collectors
ADD ./linux/bklite-controller-installer /opt/release/linux/fusion-collectors/bklite-controller-installer

# exporters
ADD ./linux/exporters /opt/release/linux/exporters
# ansible executor
ADD ./linux/ansible-executor/ ./bin/
# Suporvisor
ADD ./service.conf /etc/supervisor/conf.d/service.conf


ENTRYPOINT [ "/opt/fusion-collectors/startup.sh" ]
