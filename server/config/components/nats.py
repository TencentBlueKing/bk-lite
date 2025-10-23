import os
import ssl
from pathlib import Path

NATS_SERVERS = os.getenv("NATS_SERVERS", "")
NATS_NAMESPACE = os.getenv("NATS_NAMESPACE", "bk_lite")
NATS_JETSTREAM_ENABLED = False


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
            import logging

            logging.warning(
                f"指定的 CA 证书文件不存在: {ca_file}，将使用系统默认 CA 证书"
            )

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
    "tls_hostname": os.getenv("NATS_TLS_HOSTNAME"),  # 证书验证主机名（通过IP连接域名证书时需要）

    # 基础连接配置 - 移除 connect_timeout 避免与 nats.connect() 参数冲突
    "reconnect_time_wait": int(os.getenv("NATS_RECONNECT_WAIT", "2")),  # 重连等待时间（秒）
    "max_reconnect_attempts": int(os.getenv("NATS_MAX_RECONNECT", "60")),  # 最大重连次数

    # 认证配置（如果需要）
    "user": os.getenv("NATS_USER"),  # 用户名
    "password": os.getenv("NATS_PASSWORD"),  # 密码
    "token": os.getenv("NATS_TOKEN"),  # Token 认证
}

# 清理 None 值的配置项
NATS_OPTIONS = {k: v for k, v in NATS_OPTIONS.items() if v is not None}
