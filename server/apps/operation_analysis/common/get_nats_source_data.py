# -- coding: utf-8 --
# @File: get_nats_source_data.py
# @Time: 2025/7/22 18:24
# @Author: windyzhao
from rest_framework.exceptions import ValidationError

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.nats.nats_client import DefaultNastClient
from apps.core.utils.team_utils import get_current_team


class GetNatsData:
    """
    获取NATS数据源数据
    """

    def __init__(self, namespace: str, path: str, namespace_list: list, params: dict = None, request=None):
        self.request = request
        self.path = path
        self.params = params if params is not None else {}
        self.update_request_params()
        self.namespace = namespace
        self.namespace_list = namespace_list
        self.namespace_server_map = self.set_namespace_servers()

    @property
    def default_nats_client(self):
        return DefaultNastClient

    @property
    def default_namespace_name(self):
        return "default"

    @property
    def user_param_key(self):
        return "user_info"

    def update_request_params(self):
        """
        更新请求参数 带上当前请求的用户和组织信息
        :return:
        """
        username = self.request.user.username
        team_str = get_current_team(self.request)
        try:
            team = int(team_str)
        except (TypeError, ValueError):
            raise ValidationError("current_team cookie 缺失或格式错误，请重新登录或刷新页面")
        include_children = self.request.COOKIES.get("include_children", "0") == "1"
        permission = getattr(self.request.user, "permission", {})
        if isinstance(permission, dict):
            permission = {key: list(value) if isinstance(value, set) else value for key, value in permission.items()}
        self.params[self.user_param_key] = {
            "team": team,
            "user": username,
            "domain": self.request.user.domain,
            "timezone": getattr(self.request.user, "timezone", None),
            "permission": permission,
            "group_tree": getattr(self.request.user, "group_tree", []),
            "is_superuser": getattr(self.request.user, "is_superuser", False),
            "include_children": include_children,
        }

    def set_namespace_servers(self):
        """
        构建不含凭据的 NATS 服务器连接 URL
        根据enable_tls字段决定使用nats://或tls://协议
        """
        result = {}
        for namespace in self.namespace_list:
            # 根据enable_tls字段确定协议
            protocol = "tls" if namespace.enable_tls else "nats"

            # 凭据只在发起连接时单独传递，避免明文密码驻留在实例属性中。
            if ":" not in namespace.domain:
                # 域名不包含端口,使用默认端口4222
                server_url = f"{protocol}://{namespace.domain}:4222"
            else:
                # 域名已包含端口,直接使用
                server_url = f"{protocol}://{namespace.domain}"

            result[namespace.id] = server_url
        return result

    def _get_client(self, server, namespace):
        client = self.default_nats_client(server=server, func_name=self.path, namespace=namespace)

        return client

    def _get_target_namespace(self):
        """
        从 params 中取出 namespace_id（同时移除，避免透传给 NATS 接口），
        返回本次需要查询的单个 namespace 对象。
        若未指定则返回第一个可用 namespace。
        若显式指定但数据源未关联该命名空间，则直接报错。
        """
        namespace_id = self.params.pop("namespace_id", None)
        if namespace_id is not None:
            try:
                namespace_id = int(namespace_id)
            except (TypeError, ValueError):
                raise RuntimeError("命名空间参数无效")

        if namespace_id is not None:
            if not self.namespace_list:
                raise RuntimeError("数据源未关联命名空间")
            for ns in self.namespace_list:
                if ns.id == namespace_id:
                    return ns
            raise RuntimeError("数据源未关联所选命名空间")

        # 未指定或未匹配到，返回第一个
        return self.namespace_list[0] if self.namespace_list else None

    def get_data(self):
        """
        获取单个 namespace 的 NATS 数据源数据，保留下游返回体语义。
        """
        namespace = self._get_target_namespace()
        if namespace is None:
            raise RuntimeError("未找到可用的命名空间")

        server_url = self.namespace_server_map.get(namespace.id)
        if not server_url:
            raise RuntimeError(f"命名空间 {namespace.name} 未配置服务器连接")

        nats_namespace = getattr(namespace, "namespace", "bk_lite")
        nats_client = self._get_client(server=server_url, namespace=nats_namespace)

        if hasattr(nats_client, "DEFAULT_NATS"):
            fun = getattr(nats_client, "get_customization_nast_data", None)
        else:
            fun = getattr(nats_client, self.path, None)
        if fun is None:
            logger.warning(
                "[DataSourceQuery] 未找到接口实现 namespace=%s nats_namespace=%s path=%s",
                self.namespace, nats_namespace, self.path,
            )
            raise RuntimeError(f"NamePaces({self.namespace}) Module not found func({self.path})!")

        logger.debug(
            "[DataSourceQuery] 调用 NATS 取数 namespace=%s(id=%s) nats_namespace=%s path=%s",
            namespace.name, namespace.id, nats_namespace, self.path,
        )
        if hasattr(nats_client, "DEFAULT_NATS"):
            return fun(
                _nats_user=namespace.account,
                _nats_password=namespace.decrypt_password,
                **self.params,
            )
        return fun(**self.params)
