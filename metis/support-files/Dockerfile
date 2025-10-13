FROM python:3.12

RUN apt-get update && \
    apt-get install -y libhdf5-dev vim  unzip curl pkg-config libssl-dev libffi-dev supervisor \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 openjdk-21-jdk libxdamage1 libxfixes3 libpq-dev\ 
    libxrandr2 libgbm1 libxkbcommon0 libasound2 libatspi2.0-0 libosmesa6 libosmesa6-dev&& \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ADD . .

RUN pip install uv
RUN uv sync --all-groups
RUN uv sync --all-extras
ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

ENV TIKTOKEN_CACHE_DIR=/app/models
RUN uv run sanic server:bootstrap exec download_models

ENTRYPOINT ["/bin/bash","/app/support-files/startup.sh"]