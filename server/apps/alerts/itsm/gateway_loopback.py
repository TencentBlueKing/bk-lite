"""告警转工单访问网关时的回环改写。

完整镜像里复用 OpenAPI 回调辅助；旧镜像没有该模块时必须降级直连，
不能让 import 失败把 apps.alerts 整组路由打掉。
"""

try:
    from apps.core.openapi.async_callback import callback_tls_verify, rewrite_gateway_callback_url
except ImportError:

    def rewrite_gateway_callback_url(url):
        return url

    def callback_tls_verify(url):
        return True
