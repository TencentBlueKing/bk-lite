FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y vim  unzip curl pkg-config libssl-dev  supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ADD . .

ADD support-files/supervisor/service.conf /etc/supervisor/conf.d/service.conf
ADD support-files/supervisor/worker.conf /etc/supervisor/conf.d/worker.conf

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install uv==0.8.16

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv sync --frozen --all-groups --all-extras \
        --default-index "$NEXUS_PYTHON_REPOSITY" \
        --allow-insecure-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    else \
    uv sync --frozen --all-groups --all-extras; \
    fi

ENV PATH="/app/.venv/bin:$PATH"

RUN apt-get reinstall -y supervisor
CMD ["supervisord", "-n"]
