uv run python manage.py migrate || true
uv run python manage.py createcachetable django_cache
uv run python manage.py collectstatic --noinput

# 初始化函数定义
init_system_mgmt() {
    echo "系统管理资源初始化..."
    uv run python manage.py init_realm_resource || true
    uv run python manage.py init_login_settings || true
    uv run python manage.py create_user admin password --email=admin@bklite.net --is_superuser || true
}

init_cmdb() {
    echo "CMDB资源初始化..."
    uv run python manage.py model_init || true
}

init_console_mgmt() {
    echo "控制台管理资源初始化..."
    # 如果有控制台管理相关的初始化命令，在这里添加
}

init_monitor() {
    echo "初始化监控资源..."
    uv run python manage.py plugin_init || true
}

init_node_mgmt() {
    echo "初始化节点管理..."
    uv run python manage.py node_init || true
}

init_alerts() {
    echo "告警系统资源初始化..."
    uv run python manage.py init_alert_sources || true
    uv run python manage.py init_alert_levels || true
    uv run python manage.py create_builtin_rules --update || true
}

init_operation_analysis() {
    echo "运营分析系统资源初始化..."
    uv run python manage.py init_default_namespace || true
    uv run python manage.py init_tag  || true
    uv run python manage.py init_source_api_data --update || true
}

init_opspilot() {
    echo "OpsPilot资源初始化..."
    uv run python manage.py init_bot || true
    uv run python manage.py init_channel || true
    uv run python manage.py init_llm || true
    uv run python manage.py init_provider_model  || true
}

init_playground() {
    echo "playground资源初始化..."
    uv run python manage.py category_init || true
}



init_log(){
    echo "日志模块初始化..."
    uv run python manage.py log_init || true
}

# 读取 INSTALL_APPS 环境变量
INSTALL_APPS=${INSTALL_APPS:-""}

# 去除空白字符
INSTALL_APPS=$(echo "$INSTALL_APPS" | tr -d ' ')

# 检查是否包含 opspilot 模块
opspilot_installed=false

# 如果 INSTALL_APPS 为空，执行所有初始化
if [ -z "$INSTALL_APPS" ]; then
    init_system_mgmt
    init_cmdb
    init_monitor
    init_node_mgmt
    init_alerts
    init_operation_analysis
    init_opspilot
    init_log
    init_playground
    opspilot_installed=true
else
    # 按逗号分割 INSTALL_APPS
    IFS=',' read -ra APPS <<< "$INSTALL_APPS"
    
    for app in "${APPS[@]}"; do
        case "$app" in
            "log")
                init_log
                ;;
            "system_mgmt")
                init_system_mgmt
                ;;
            "cmdb")
                init_cmdb
                ;;
            "console_mgmt")
                init_console_mgmt
                ;;
            "monitor")
                init_monitor
                ;;
            "node_mgmt")
                init_node_mgmt
                ;;
            "alerts")
                init_alerts
                ;;
            "operation_analysis")
                init_operation_analysis
                ;;
            "playground")
                init_playground
                ;;
            "opspilot")
                init_opspilot
                opspilot_installed=true
                ;;
            *)
                echo "未知模块: $app"
                ;;
        esac
    done
fi

# 如果没有安装 opspilot 模块，删除 consumer.conf 文件
if [ "$opspilot_installed" = false ]; then
    echo "未安装 opspilot 模块，删除 consumer.conf 配置文件..."
    rm -f /etc/supervisor/conf.d/consumer.conf
fi

# 设置进程数量环境变量默认值
export APP_WORKERS=${APP_WORKERS:-8}
export CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-4}
export NATS_NUMPROCS=${NATS_NUMPROCS:-4}

echo "进程配置:"
echo "  APP_WORKERS=$APP_WORKERS"
echo "  CELERY_CONCURRENCY=$CELERY_CONCURRENCY"
echo "  NATS_NUMPROCS=$NATS_NUMPROCS"

supervisord -n