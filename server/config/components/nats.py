import os
import ssl
from pathlib import Path

from loguru import logger


def _read_number(name, default, cast, minimum):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = cast(raw_value)
    except (TypeError, ValueError):
        logger.warning("NATS 配置 {}={!r} 非法，使用默认值 {}", name, raw_value, default)
        return default
    if value < minimum:
        logger.warning("NATS 配置 {}={!r} 小于下限 {}，使用下限", name, raw_value, minimum)
        return minimum
    return value


NATS_SERVERS = os.getenv("NATS_SERVERS", "")
NATS_NAMESPACE = os.getenv("NATS_NAMESPACE", "bklite")
NATS_JETSTREAM_ENABLED = False
NATS_HANDLER_CONCURRENCY = _read_number("NATS_HANDLER_CONCURRENCY", 64, int, 1)
NATS_HANDLER_QUEUE_SIZE = _read_number("NATS_HANDLER_QUEUE_SIZE", 1024, int, 1)
NATS_HANDLER_ENQUEUE_TIMEOUT = _read_number("NATS_HANDLER_ENQUEUE_TIMEOUT", 5.0, float, 0.1)
# 显式保留 nats-py 的既有 pending 上限，避免升级后缩小合法突发流量的缓冲契约。
NATS_CORE_PENDING_MSGS_LIMIT = _read_number(
    "NATS_CORE_PENDING_MSGS_LIMIT",
    512 * 1024,
    int,
    1,
)
NATS_CORE_PENDING_BYTES_LIMIT = _read_number("NATS_CORE_PENDING_BYTES_LIMIT", 128 * 1024 * 1024, int, 1)
NATS_JETSTREAM_IN_PROGRESS_INTERVAL = _read_number("NATS_JETSTREAM_IN_PROGRESS_INTERVAL", 10.0, float, 0.1)
NATS_FETCH_RETRY_DELAY = _read_number("NATS_FETCH_RETRY_DELAY", 1.0, float, 0.0)
NATS_HANDLER_SHUTDOWN_TIMEOUT = _read_number("NATS_HANDLER_SHUTDOWN_TIMEOUT", 30.0, float, 0.1)


def _create_ssl_context():
    """创建 SSL 上下文用于 TLS 连接

    环境变量说明：
    - NATS_TLS_ENABLED: 是否启用 TLS (true/false)，默认 false
    - NATS_TLS_INSECURE: 是否跳过证书验证 (true/false)，默认 false
    - NATS_TLS_CA_FILE: 自定义 CA 证书文件路径（可选，用于企业内部CA或自签名证书）
    - NATS_TLS_HOSTNAME: 强制指定证书验证的主机名（可选）
    - NATS_TLS_CERT_FILE: 客户端证书文件路径（可选）
    - NATS_TLS_KEY_FILE: 客户端私钥文件路径（可选）
    """
    if not os.getenv("NATS_TLS_ENABLED", "false").lower() == "true":
        return None

    # 检查自定义 CA 证书文件
    ca_file = os.getenv("NATS_TLS_CA_FILE")
    if ca_file and Path(ca_file).exists():
        # 使用自定义 CA 证书（企业内部 CA 或自签名证书）
        ssl_context = ssl.create_default_context(cafile=ca_file)
    else:
        # 使用系统默认 CA 证书（适用于公共 CA 签发的证书）
        ssl_context = ssl.create_default_context()
        # 如果指定了 CA 文件但文件不存在，记录警告
        if ca_file:
            logger.warning("指定的 CA 证书文件不存在: {}，将使用系统默认 CA 证书", ca_file)

    # 是否跳过证书验证（用于测试环境）
    if os.getenv("NATS_TLS_INSECURE", "false").lower() == "true":
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    # 客户端证书认证（可选）
    cert_file = os.getenv("NATS_TLS_CERT_FILE")
    key_file = os.getenv("NATS_TLS_KEY_FILE")
    if cert_file and key_file and Path(cert_file).exists() and Path(key_file).exists():
        ssl_context.load_cert_chain(cert_file, key_file)

    return ssl_context


# NATS 连接选项 - 只保留常用和必要的配置项
NATS_OPTIONS = {
    # TLS 配置
    "tls": _create_ssl_context(),
    "tls_hostname": os.getenv(
        "NATS_TLS_HOSTNAME"
    ),  # 证书验证主机名（通过IP连接域名证书时需要）
    # 基础连接配置 - 移除 connect_timeout 避免与 nats.connect() 参数冲突
    "reconnect_time_wait": int(
        os.getenv("NATS_RECONNECT_WAIT", "2")
    ),  # 重连等待时间（秒）
    "max_reconnect_attempts": int(
        os.getenv("NATS_MAX_RECONNECT", "60")
    ),  # 最大重连次数
    # 认证配置（如果需要）
    "user": os.getenv("NATS_USER"),  # 用户名
    "password": os.getenv("NATS_PASSWORD"),  # 密码
    "token": os.getenv("NATS_TOKEN"),  # Token 认证
}

# 清理 None 值的配置项
NATS_OPTIONS = {k: v for k, v in NATS_OPTIONS.items() if v is not None}
