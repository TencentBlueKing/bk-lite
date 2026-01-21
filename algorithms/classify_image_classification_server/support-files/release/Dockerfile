FROM python:3.12
WORKDIR /apps
ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update -y
RUN apt-get install -y \
    vim \
    supervisor \
    unzip \
    curl \
    fonts-wqy-zenhei \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 更新系统字体缓存
RUN fc-cache -fv

# 配置 pip 镜像源（如果提供）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

# 安装 uv (Python 包管理工具)
RUN pip3 install uv

# 优化：先复制依赖文件，利用 Docker 缓存
COPY pyproject.toml uv.lock* ./

# 使用 uv 安装所有依赖
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv pip install --system --index-url "$NEXUS_PYTHON_REPOSITY" -e .; \
    else \
    uv pip install --system -e .; \
    fi

# 复制项目代码
ADD . .

# 设置脚本和 mc 可执行权限
RUN chmod +x ./support-files/release/startup.sh && \
    chmod +x ./support-files/scripts/train-model.sh && \
    chmod +x ./mc

# 快速同步检查（验证依赖完整性）
RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    uv sync --index-url "$NEXUS_PYTHON_REPOSITY"; \
    else \
    uv sync; \
    fi

# 清理 matplotlib 字体缓存，让其重新扫描字体
RUN rm -rf /root/.cache/matplotlib /root/.cache/fontconfig

RUN apt-get reinstall -y supervisor

ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]