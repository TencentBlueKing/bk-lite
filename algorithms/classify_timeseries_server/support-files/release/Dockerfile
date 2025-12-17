FROM python:3.12
WORKDIR /apps
ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y
RUN apt-get install -y vim supervisor unzip curl

# 安装 uv (Python 包管理工具)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

ADD . .

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

# 设置脚本和 mc 可执行权限
RUN chmod +x ./support-files/release/startup.sh && \
    chmod +x ./support-files/scripts/train-model.sh && \
    chmod +x ./mc

# 配置 uv PyPI 镜像源（如果提供）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv pip config set index-url "$NEXUS_PYTHON_REPOSITY"; \
    fi

# 使用 uv 安装项目依赖
RUN uv pip install --system -e ".[dev]"

RUN apt-get reinstall -y supervisor 

ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]