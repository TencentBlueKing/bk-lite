"""webhookd 渲染请求的 TLS 校验配置。

云区域配置采集（log / monitor / cmdb）会把云区域级 NATS 凭据交给 webhookd
渲染 K8s 采集 YAML。历史实现对该 HTTPS 请求硬编码 ``verify=False`` 关闭证书校验，
存在两个高危后果：凭据被中间人窃取、返回的 YAML 被篡改后经 ``kubectl apply`` 在
目标集群执行。此处提供按环境变量可配置、默认安全的校验策略，替换硬编码关闭。
"""

import os


def get_webhook_tls_verify():
    """返回传给 ``requests`` 的 ``verify`` 参数（secure-by-default）。

    环境变量 ``WEBHOOK_SERVER_SSL_VERIFY``：
      - 未配置 / ``"true"`` / ``"1"`` / ``"yes"`` → ``True``（按系统 CA 校验，默认）
      - ``"false"`` / ``"0"`` / ``"no"``        → ``False``（显式内网自签名 opt-out）
      - 其它非空值                              → 视为受信 CA 证书/bundle 路径
        （``requests`` 的 ``verify`` 接受 CA 文件/目录路径字符串）
    """
    raw = (os.getenv("WEBHOOK_SERVER_SSL_VERIFY") or "true").strip()
    lowered = raw.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    return raw
