FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl coreutils ca-certificates fonts-wqy-microhei git jq ripgrep nodejs npm \
    libcairo2 libpango-1.0-0 poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv numpy pandas openpyxl matplotlib reportlab \
       python-docx python-pptx pypdf pdfplumber pypdfium2 pillow cairosvg lxml pyyaml kubernetes \
    && ln -s /workspace/skills /skills \
    && ln -s /workspace/ppt-workspace /ppt-workspace

RUN apt-get update && apt-get install -y --no-install-recommends zip unzip file \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir requests jinja2 markdown-it-py ijson

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONUSERBASE=/workspace/.local PIP_NO_CACHE_DIR=1 \
    NPM_CONFIG_PREFIX=/workspace/.local NPM_CONFIG_CACHE=/workspace/.cache/npm \
    NPM_CONFIG_UPDATE_NOTIFIER=false UV_CACHE_DIR=/workspace/.cache/uv \
    PATH="/workspace/.local/bin:${PATH}"
COPY USAGE.md /opt/opspilot-sandbox/USAGE.md
WORKDIR /workspace
