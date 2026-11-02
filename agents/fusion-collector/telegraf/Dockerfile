FROM telegraf:1.32 as builder

FROM ubuntu:24.04

# CVE-2026-111497：更新系统解码库；软件源未提供补丁时禁止生成发行镜像。
RUN apt-get update && \
    apt-get install -y --no-install-recommends libbrotli1 && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge '1.1.0-2ubuntu0.1' && \
    rm -rf /var/lib/apt/lists/*
RUN sed -i "s@http://.*.ubuntu.com@http://repo.huaweicloud.com@g" /etc/apt/sources.list.d/ubuntu.sources 
RUN apt-get update && \
    apt-get install -y snmptrapd ca-certificates ipmitool vim snmp supervisor zip iputils-ping && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ADD ./mibs /usr/share/snmp/mibs

WORKDIR /apps
ADD ./telegraf.conf ./telegraf.conf
COPY --from=builder /usr/bin/telegraf ./telegraf
ADD ./service.conf /etc/supervisor/conf.d/service.conf
ADD ./startup.sh ./startup.sh

RUN chmod -Rf 777 /apps/*

ENTRYPOINT ["/bin/bash", "/apps/startup.sh" ]
