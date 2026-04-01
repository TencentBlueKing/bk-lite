FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

WORKDIR /apps

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y vim supervisor nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install browser-use/patchright dependencies: system libraries and fonts for headless Chromium
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        fonts-unifont \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-freefont-ttf \
        fonts-noto-core \
        libnss3 \
        libxss1 \
        libasound2 \
        libx11-xcb1 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libxshmfence1 \
        libxfixes3 \
        libglu1-mesa && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver 18 for SQL Server (required for pyodbc compilation)
# Installation may fail in restricted networks, but won't block the build
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list | tee /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* || \
    echo "Warning: MSSQL ODBC driver installation failed, MSSQL tools will not be available"

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

RUN npm install -g agent-browser && \
    agent-browser install --with-deps && \
    agent-browser --version && \
    npm cache clean --force

RUN PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright patchright install chromium

ENV EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome

RUN chmod +x ./support-files/release/startup.sh

RUN apt-get reinstall -y supervisor

ENTRYPOINT ["/bin/bash", "/apps/support-files/release/startup.sh"]
