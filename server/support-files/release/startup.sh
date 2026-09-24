if python3 manage.py migrate; then
    :
else
    migrate_status=$?
    echo "数据库迁移失败，停止启动；请修复迁移问题后重新启动容器" >&2
    exit "$migrate_status"
fi
python3 manage.py createcachetable django_cache
python3 manage.py collectstatic --noinput

# 读取 INSTALL_APPS 环境变量
INSTALL_APPS=${INSTALL_APPS:-""}

# 去除空白字符
INSTALL_APPS=$(echo "$INSTALL_APPS" | tr -d ' ')

# 使用统一的批量初始化命令，在单个 Python 进程中完成所有初始化
# 大幅减少启动时间（从原来的多次 Python 进程启动优化为单次启动）
echo "开始批量初始化..."
if ! python3 manage.py batch_init --apps="$INSTALL_APPS"; then
    echo "批量初始化失败，停止启动"
    exit 1
fi

# 检查是否包含 opspilot 模块
opspilot_installed=false
workflow_orchestration_installed=false
if [ -z "$INSTALL_APPS" ]; then
    # 空表示安装所有模块
    opspilot_installed=true
    workflow_orchestration_installed=true
else
    case ",$INSTALL_APPS," in
        *,opspilot,*) opspilot_installed=true ;;
    esac
    case ",$INSTALL_APPS," in
        *,workflow_orchestration,*) workflow_orchestration_installed=true ;;
    esac
fi

# 未安装 opspilot 时不拉起专用 worker；consumer.conf 是历史文件，一并清掉
SUPERVISOR_CONF_DIR=${SUPERVISOR_CONF_DIR:-/etc/supervisor/conf.d}
if [ "$opspilot_installed" = false ]; then
    echo "未安装 opspilot 模块，删除 opspilot 专用 supervisor 配置..."
    rm -f "$SUPERVISOR_CONF_DIR/consumer.conf"
    rm -f "$SUPERVISOR_CONF_DIR/opspilot_celery.conf"
fi

# 编排 Worker、触发调度和产物清理由同一配置管理，只在安装编排中心时运行。
if [ "$workflow_orchestration_installed" = false ]; then
    echo "未安装 workflow_orchestration 模块，删除编排中心 supervisor 配置..."
    rm -f "$SUPERVISOR_CONF_DIR/workflow_orchestration_worker.conf"
fi


# 设置进程数量环境变量默认值
export APP_WORKERS=${APP_WORKERS:-8}
export CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-2}
# 子进程回收：任务数或 RSS（KB）超限后退出，仅对 prefork 生效。Beat 不要设置这两项。
export CELERY_MAX_TASKS_PER_CHILD=${CELERY_MAX_TASKS_PER_CHILD:-200}
export CELERY_MAX_MEMORY_PER_CHILD=${CELERY_MAX_MEMORY_PER_CHILD:-512000}
export DASHBOARD_REPORT_RENDER_CONCURRENCY=${DASHBOARD_REPORT_RENDER_CONCURRENCY:-2}
export OPSPILOT_CELERY_CONCURRENCY=${OPSPILOT_CELERY_CONCURRENCY:-2}
export NATS_NUMPROCS=${NATS_NUMPROCS:-4}

echo "进程配置:"
echo "  APP_WORKERS=$APP_WORKERS"
echo "  CELERY_CONCURRENCY=$CELERY_CONCURRENCY"
echo "  CELERY_MAX_TASKS_PER_CHILD=$CELERY_MAX_TASKS_PER_CHILD"
echo "  CELERY_MAX_MEMORY_PER_CHILD=$CELERY_MAX_MEMORY_PER_CHILD"
echo "  DASHBOARD_REPORT_RENDER_CONCURRENCY=$DASHBOARD_REPORT_RENDER_CONCURRENCY"
echo "  OPSPILOT_CELERY_CONCURRENCY=$OPSPILOT_CELERY_CONCURRENCY"
echo "  NATS_NUMPROCS=$NATS_NUMPROCS"

supervisord -n
