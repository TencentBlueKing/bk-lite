FROM python:3.12
WORKDIR /apps
ARG NEXUS_PYTHON_REPOSITY

#RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

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


ADD . .

# 设置脚本可执行权限
RUN chmod +x ./support-files/release/startup.sh && \
    chmod +x ./support-files/scripts/train-model.sh

# 使用 pip 安装项目依赖
RUN pip3 install -e ".[dev]"

# 清理 matplotlib 字体缓存，让其重新扫描字体
RUN rm -rf /root/.cache/matplotlib /root/.cache/fontconfig

RUN apt-get reinstall -y supervisor

# 链接 supervisor 配置文件到默认配置目录
RUN mkdir -p /etc/supervisor/conf.d && \
    ln -sf /apps/support-files/release/supervisor/app.conf /etc/supervisor/conf.d/app.conf


ADD https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt /apps/yolo_models/yolo11n.pt
ADD https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11x.pt /apps/yolo_models/yolo11x.pt
ADD https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11s.pt /apps/yolo_models/yolo11s.pt
ADD https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11m.pt /apps/yolo_models/yolo11m.pt
ADD https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11l.pt /apps/yolo_models/yolo11l.pt

ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]