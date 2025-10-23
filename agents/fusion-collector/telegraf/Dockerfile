FROM telegraf:1.32 as builder

FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y ca-certificates ipmitool vim snmp supervisor zip iputils-ping && \
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