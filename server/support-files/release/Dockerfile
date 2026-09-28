FROM ghcr.io/tencentblueking/bk-lite/server-base:latest

ARG NEXUS_PYTHON_REPOSITY

WORKDIR /apps

ADD ./support-files/release/supervisor/app.conf  /etc/supervisor/conf.d/app.conf
ADD ./support-files/release/supervisor/nats.conf  /etc/supervisor/conf.d/nats.conf
ADD ./support-files/release/supervisor/beat.conf  /etc/supervisor/conf.d/beat.conf
ADD ./support-files/release/supervisor/celery.conf  /etc/supervisor/conf.d/celery.conf
ADD ./support-files/release/supervisor/patch_maintenance.conf  /etc/supervisor/conf.d/patch_maintenance.conf
ADD ./support-files/release/supervisor/dashboard_report_render_worker.conf  /etc/supervisor/conf.d/dashboard_report_render_worker.conf
ADD ./support-files/release/supervisor/opspilot_celery.conf  /etc/supervisor/conf.d/opspilot_celery.conf
ADD ./support-files/release/supervisor/workflow_orchestration_worker.conf  /etc/supervisor/conf.d/workflow_orchestration_worker.conf
# 默认 release 容器启动时也要带上 SNMP Trap bridge，
# 否则即使仓库里存在 conf 文件，supervisor 也不会实际加载它。
ADD ./support-files/release/supervisor/snmp_trap_bridge.conf  /etc/supervisor/conf.d/snmp_trap_bridge.conf

ADD . .

RUN if [ -n "$NEXUS_PYTHON_REPOSITY" ]; then \
    pip3 config set global.index-url "$NEXUS_PYTHON_REPOSITY" && \
    pip3 config set global.trusted-host "$(echo $NEXUS_PYTHON_REPOSITY | sed -E 's|^https?://([^/:]+).*|\1|')"; \
    fi

RUN pip3 install -e ".[cmdb,dev,mlops,opspilot]"

# 构建期拉取 tiktoken 词表到本地缓存，运行容器无需访问 Azure。
# cl100k_base：未知模型回退；o200k_base：gpt-4o 等默认编码器。
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache
RUN mkdir -p /opt/tiktoken_cache \
    && python3 -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"

RUN chmod +x ./support-files/release/startup.sh

RUN apt-get reinstall -y supervisor

ENTRYPOINT ["/bin/bash", "/apps/support-files/release/startup.sh"]
