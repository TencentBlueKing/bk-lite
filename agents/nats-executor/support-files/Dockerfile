FROM ubuntu:24.04

RUN sed -i "s@http://.*.ubuntu.com@http://repo.huaweicloud.com@g"  /etc/apt/sources.list.d/ubuntu.sources 
ENV NATS_INSTANCE_ID "default"
ENV NATS_URLS "nats://admin:password@nats:4222"

RUN apt-get update && \
    apt-get install -y  sshpass supervisor&& \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ADD ./nats-executor /opt/nats-executor
ADD ./support-files/startup.sh /opt/startup.sh
ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

RUN chmod +x /opt/startup.sh
RUN chmod +x /opt/nats-executor

ENTRYPOINT [ "/bin/bash", "/opt/startup.sh" ]
