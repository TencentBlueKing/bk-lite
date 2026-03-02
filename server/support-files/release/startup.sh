python3 manage.py migrate || true
python3 manage.py createcachetable django_cache
python3 manage.py collectstatic --noinput

# 读取 INSTALL_APPS 环境变量
INSTALL_APPS=${INSTALL_APPS:-""}

# 去除空白字符
INSTALL_APPS=$(echo "$INSTALL_APPS" | tr -d ' ')

# 使用统一的批量初始化命令，在单个 Python 进程中完成所有初始化
# 大幅减少启动时间（从原来的多次 Python 进程启动优化为单次启动）
echo "开始批量初始化..."
python3 manage.py batch_init --apps="$INSTALL_APPS" || true

# 检查是否包含 opspilot 模块
opspilot_installed=false
if [ -z "$INSTALL_APPS" ]; then
    # 空表示安装所有模块，包括 opspilot
    opspilot_installed=true
elif echo "$INSTALL_APPS" | grep -q "opspilot"; then
    opspilot_installed=true
fi

# 如果没有安装 opspilot 模块，删除 consumer.conf 文件
if [ "$opspilot_installed" = false ]; then
    echo "未安装 opspilot 模块，删除 consumer.conf 配置文件..."
    rm -f /etc/supervisor/conf.d/consumer.conf
fi

# 如果安装了 opspilot 模块，检查并安装 MSSQL ODBC 驱动
if [ "$opspilot_installed" = true ]; then
    if ! odbcinst -q -d -n "ODBC Driver 18 for SQL Server" > /dev/null 2>&1; then
        echo "正在安装 Microsoft ODBC Driver 18 for SQL Server..."
        if curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
           curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list | tee /etc/apt/sources.list.d/mssql-release.list > /dev/null && \
           apt-get update -qq && \
           ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18; then
            apt-get clean
            rm -rf /var/lib/apt/lists/*
            echo "MSSQL ODBC 驱动安装完成"
        else
            echo "警告: MSSQL ODBC 驱动安装失败，MSSQL 相关工具将不可用，但不影响其他功能"
        fi
    else
        echo "MSSQL ODBC 驱动已安装，跳过"
    fi
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