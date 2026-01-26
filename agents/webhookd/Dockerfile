FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && \
    apt-get install -y vim  unzip wget curl pkg-config libssl-dev supervisor gettext-base jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ADD ./bin/webhookd /usr/local/bin/webhookd
ADD ./bin/runc /usr/local/bin/runc
ADD ./bin/mc /usr/local/bin/mc
ADD ./bin/docker-proxy /usr/local/bin/docker-proxy
ADD ./bin/docker-init /usr/local/bin/docker-init
ADD ./bin/dockerd /usr/local/bin/dockerd
ADD ./bin/docker-compose /usr/local/bin/docker-compose
ADD ./bin/docker /usr/local/bin/docker
ADD ./bin/ctr /usr/local/bin/ctr
ADD ./bin/containerd-shim-runc-v2 /usr/local/bin/containerd-shim-runc-v2
ADD ./bin/containerd /usr/local/bin/containerd

WORKDIR /apps/scripts
ADD ./compose /apps/scripts/compose
ADD ./kubernetes /apps/scripts/kubernetes
ADD ./common.sh /apps/scripts/common.sh
ADD ./infra /apps/scripts/infra
ADD ./*.yaml /apps/scripts/

RUN chmod -Rf 777 /apps/scripts
CMD ["/usr/local/bin/webhookd", "-hook-default-mode","buffered","-hook-scripts","/apps/scripts","-hook-timeout", "30"]