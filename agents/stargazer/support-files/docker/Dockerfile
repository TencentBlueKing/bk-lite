FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y vim  unzip curl pkg-config libssl-dev  supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Sanic 进程数，默认 1。采集 Run 绑定在接收请求的进程内不跨进程，且每个进程各持一份
# MAX_ACTIVE_TARGETS：调大只能分摊多个独立 Run，容器总并发会按倍数放大。确认容器
# 并发口径后再用 -e SANIC_WORKERS=N 显式放开。
ENV SANIC_WORKERS=1

WORKDIR /app

ADD . .

ADD support-files/supervisor/service.conf /etc/supervisor/conf.d/service.conf

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install -e ".[dev,aliyun,qcloud,huawei,vmware,openstack,qingyun,snmp]"
RUN apt-get reinstall -y supervisor 
CMD ["supervisord", "-n"]
