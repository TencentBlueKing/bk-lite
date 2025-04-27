FROM telegraf:1.33.3

RUN apt-get update && \
    apt-get install -y ca-certificates ipmitool vim&& \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*
    
ADD ./mibs /usr/share/snmp/mibs
ADD ./telegraf.conf /etc/telegraf/telegraf.conf

