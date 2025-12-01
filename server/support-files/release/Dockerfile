FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

WORKDIR /apps

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y vim supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ADD ./support-files/release/supervisor/app.conf  /etc/supervisor/conf.d/app.conf
ADD ./support-files/release/supervisor/nats.conf  /etc/supervisor/conf.d/nats.conf
ADD ./support-files/release/supervisor/beat.conf  /etc/supervisor/conf.d/beat.conf
ADD ./support-files/release/supervisor/celery.conf  /etc/supervisor/conf.d/celery.conf

ADD . .

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install -e ".[cmdb,dev,mlops,opspilot]"

RUN chmod +x ./support-files/release/startup.sh
RUN apt-get reinstall -y supervisor 
ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]