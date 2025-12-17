FROM python:3.12
WORKDIR /apps
ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y
RUN apt-get install -y vim supervisor unzip curl fonts-noto-cjk

# 清理 matplotlib 字体缓存
RUN rm -rf /root/.cache/matplotlib

# 配置 pip 镜像源（如果提供）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

# 安装 uv (Python 包管理工具)
RUN pip3 install uv

ADD . .

# 设置脚本和 mc 可执行权限
RUN chmod +x ./support-files/release/startup.sh && \
    chmod +x ./support-files/scripts/train-model.sh && \
    chmod +x ./mc

# 使用 uv 安装项目依赖（通过命令行参数指定镜像源）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv pip install --system --index-url "$NEXUS_PYTHON_REPOSITY" -e ".[dev]"; \
    else \
    uv pip install --system -e ".[dev]"; \
    fi

RUN apt-get reinstall -y supervisor 

ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]