FROM python:3.12

ARG NEXUS_PYTHON_REPOSITY

RUN sed -i 's/deb.debian.org/repo.huaweicloud.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y vim  unzip curl pkg-config libssl-dev  supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Sanic 进程数：每进程独立 GIL，用于绕开单进程 CPU 天花板；可在运行时用 -e 覆盖
ENV SANIC_WORKERS=4

WORKDIR /app

ADD . .

# Enterprise 只能来自 Makefile 校验过的主仓库子模块 named context；主 context
# 中的同名忽略目录不会进入镜像，避免历史副本静默覆盖 gitlink 版本。
COPY --from=enterprise_src . ./enterprise

ARG ENTERPRISE_SHA
RUN test -n "$ENTERPRISE_SHA" && printf '%s\n' "$ENTERPRISE_SHA" > /app/enterprise/.source-git-sha
LABEL com.weops.stargazer.enterprise.revision="$ENTERPRISE_SHA"

ADD support-files/supervisor/service.conf /etc/supervisor/conf.d/service.conf

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install -e ".[dev,aliyun,qcloud,huawei,vmware,openstack,qingyun,snmp]"

# 构建期即验证本次事故涉及的 Enterprise 插件入口，禁止坏镜像进入仓库。
RUN python3 -c "import enterprise.plugins.inputs.sangforhci.sangforhci_info; import enterprise.plugins.inputs.sangforscp.sangforscp_info"

RUN apt-get reinstall -y supervisor 
CMD ["supervisord", "-n"]
