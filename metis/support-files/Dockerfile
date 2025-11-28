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

ADD . .

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install -e ".[dev,core,sanic,mlflow,doc_parser,mlops,llm,devops,ocr]"
ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

ENV TIKTOKEN_CACHE_DIR=/app/models
RUN apt-get reinstall -y supervisor 
ENTRYPOINT ["/bin/bash","/app/support-files/startup.sh"]