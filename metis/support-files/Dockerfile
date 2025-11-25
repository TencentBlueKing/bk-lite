FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y libhdf5-dev vim  unzip curl pkg-config libssl-dev libffi-dev supervisor \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 openjdk-21-jdk libxdamage1 libxfixes3 libpq-dev\ 
    libxrandr2 libgbm1 libxkbcommon0 libasound2 libatspi2.0-0 libosmesa6 libosmesa6-dev&& \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 如果提供了 NEXUS_PYTHON_REPOSITY,则切换 pip 源
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    echo "Setting pip index to: $NEXUS_PYTHON_REPOSITY"; \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY"; \
    if echo "$NEXUS_PYTHON_REPOSITY" | grep -q "^http://"; then \
    TRUSTED_HOST=$(echo "$NEXUS_PYTHON_REPOSITY" | sed -E 's|^http://([^/:]+).*|\1|'); \
    echo "Adding trusted host: $TRUSTED_HOST"; \
    pip3 config set global.trusted-host "$TRUSTED_HOST"; \
    fi; \
    else \
    echo "Using default pip index"; \
    fi

ADD . .

RUN pip3 install uv

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    echo "Using custom Python index: $NEXUS_PYTHON_REPOSITY"; \
    if echo "$NEXUS_PYTHON_REPOSITY" | grep -q "^http://"; then \
    TRUSTED_HOST=$(echo "$NEXUS_PYTHON_REPOSITY" | sed -E 's|^http://([^/:]+).*|\1|'); \
    uv sync --all-groups --index-url "$NEXUS_PYTHON_REPOSITY" --trusted-host "$TRUSTED_HOST"; \
    uv sync --all-extras --index-url "$NEXUS_PYTHON_REPOSITY" --trusted-host "$TRUSTED_HOST"; \
    else \
    uv sync --all-groups --index-url "$NEXUS_PYTHON_REPOSITY"; \
    uv sync --all-extras --index-url "$NEXUS_PYTHON_REPOSITY"; \
    fi; \
    else \
    uv sync --all-groups; \
    uv sync --all-extras; \
    fi
ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

ENV TIKTOKEN_CACHE_DIR=/app/models

ENTRYPOINT ["/bin/bash","/app/support-files/startup.sh"]