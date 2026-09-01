import uuid
from urllib.parse import urlsplit, urlunsplit

from jinja2 import BaseLoader, DebugUndefined
from jinja2.defaults import DEFAULT_FILTERS

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.safe_template import TemplateSecurityError, build_sandboxed_env, sanitize_template_context, validate_template_variables
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import CollectConfig, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.website_config import normalize_website_request_config
from apps.monitor.utils.dimension import parse_instance_id
from apps.rpc.node_mgmt import NodeMgmt

_MONITOR_TEMPLATE_ALLOWED_FILTERS = (
    "default",
    "join",
    "lower",
    "urlencode",
    "replace",
    "to_toml_str_array",
)
_MONITOR_TEMPLATE_ALLOWED_VARIABLES = {
    # SNMP 接口过滤运行时注入片段的固定 Jinja 局部变量。
    "_ifdescr_exclude",
    "_ifdescr_include",
    "_iftype_exclude",
    "_iftype_include",
    "ENV_BEARER_TOKEN",
    "ENV_PASSWORD",
    "agents",
    "auth_password",
    "auth_protocol",
    "auth_type",
    "base_url",
    "client_timeout",
    "collector",
    "collect_queues",
    "collect_type",
    "community",
    "config_id",
    "credential_encoding",
    "database",
    "dbname",
    "disk_exclude_fstypes",
    "disk_include_fstypes",
    "enable_ifmib",
    "endpoint",
    "ews_url",
    "expect",
    "host",
    "ifdescr_exclude",
    "ifdescr_include",
    "ifmib_capable",
    "iftype_exclude",
    "iftype_include",
    "insecure_skip_verify",
    "instance_id",
    "instance_type",
    "interval",
    "ip",
    "ip_version",
    "jmx_url",
    "ldap_port",
    "ldaps_port",
    "logical_instance_value",
    "metric_extensions",
    "metrics_api_version",
    "metrics_modules",
    "monitor_plugin_id",
    "namespace",
    "node_id",
    "os_type",
    "owa_url",
    "password",
    "pattern",
    "plugin_id",
    "port",
    "ports",
    "private_key_content",
    "private_key_passphrase",
    "priv_password",
    "priv_protocol",
    "process_name",
    "protocol",
    "queue_name_exclude",
    "queue_name_include",
    "request_body",
    "request_headers",
    "request_method",
    "request_url",
    "response_timeout",
    "response_status_code",
    "response_string_match",
    "follow_redirects",
    "gather_binary_logs",
    "gather_global_variables",
    "gather_innodb_metrics",
    "gather_process_list",
    "gather_replica_status",
    "gather_slave_status",
    "gather_table_io_waits",
    "gather_table_lock_waits",
    "sec_level",
    "sec_name",
    "send",
    "server",
    "server_url",
    "scheme",
    "sslmode",
    "storage_instance_key",
    "timeout",
    "tls_ca",
    "tls_cert",
    "tls_key",
    "type",
    "url",
    "username",
    "version",
    "winrm_cert_validation",
    "winrm_scheme",
    "winrm_transport",
}


def _escape_toml_string(value):
    if not isinstance(value, str):
        value = str(value)
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def to_toml_dict(d):
    """将字典转换为 TOML 格式的内联表"""
    if not d:
        return "{}"
    return "{ " + ", ".join(f'"{_escape_toml_string(k)}" = "{_escape_toml_string(v)}"' for k, v in d.items()) + " }"


def to_toml_str_array(value):
    """将列表或逗号分隔字符串转为 TOML 字符串数组字面量，如 ["24", "53"]。"""
    from apps.monitor.utils.snmp_interface_filters import normalize_filter_list

    items = normalize_filter_list(value)
    return "[" + ", ".join(f'"{_escape_toml_string(item)}"' for item in items) + "]"


def normalize_filter_list(value):
    """兼容旧导入路径；实现见 snmp_interface_filters.normalize_filter_list。"""
    from apps.monitor.utils.snmp_interface_filters import normalize_filter_list as _normalize_filter_list

    return _normalize_filter_list(value)


def _escape_toml_context_strings(value):
    if isinstance(value, str):
        return _escape_toml_string(value)
    if isinstance(value, dict):
        return {key: _escape_toml_context_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_escape_toml_context_strings(item) for item in value]
    return value


def normalize_rabbitmq_management_url(url):
    """Collapse duplicate slashes and strip a trailing slash from a RabbitMQ Management URL.

    Happy path is the Management root with no path, e.g. http://127.0.0.1:15672.
    If a path was typed, keep it after cleanup: http://host:15672///api -> http://host:15672/api.
    Invalid or empty values are returned as stripped text so existing UI validators remain the gate.
    """
    if url in (None, ""):
        return url
    text = str(url).strip()
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return text
    path = parts.path or ""
    while "//" in path:
        path = path.replace("//", "/")
    if path in {"", "/"}:
        path = ""
    else:
        path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _is_rabbitmq_collect_config(config: dict) -> bool:
    return str(config.get("type") or config.get("instance_type") or "").lower() == "rabbitmq"


def _normalize_template_context(context: dict) -> dict:
    normalized = {**context}
    metrics_modules = normalized.get("metrics_modules")
    if isinstance(metrics_modules, (list, tuple)):
        normalized["metrics_modules"] = ",".join(str(item).strip() for item in metrics_modules if str(item).strip())
    for key in ("winrm_cert_validation",):
        if isinstance(normalized.get(key), bool):
            normalized[key] = "true" if normalized[key] else "false"
    # Process 端口存活：逗号串/列表统一为 list[str]；缺失或空 → []，模板可安全跳过。
    from apps.monitor.utils.snmp_interface_filters import normalize_filter_list

    normalized["ports"] = normalize_filter_list(normalized.get("ports"))
    if _is_rabbitmq_collect_config(normalized) and normalized.get("url") not in (None, ""):
        normalized["url"] = normalize_rabbitmq_management_url(normalized.get("url"))
    return normalized


class Controller:
    def __init__(self, data):
        self.data = data
        # 优化：复用 Jinja2 Environment 对象，避免重复创建
        self._jinja_env = None

    @property
    def jinja_env(self):
        """延迟初始化并缓存 Jinja2 SandboxedEnvironment 对象"""
        if self._jinja_env is None:
            env = build_sandboxed_env(
                loader=BaseLoader(),
                undefined=DebugUndefined,
                extra_filters={
                    "to_toml": to_toml_dict,
                    "to_toml_str_array": to_toml_str_array,
                },
            )
            missing_filters = [name for name in _MONITOR_TEMPLATE_ALLOWED_FILTERS if name not in DEFAULT_FILTERS and name not in env.filters]
            if missing_filters:
                raise BaseAppException(f"Missing default Jinja filters: {', '.join(missing_filters)}")
            env.filters.update({name: DEFAULT_FILTERS[name] for name in _MONITOR_TEMPLATE_ALLOWED_FILTERS if name in DEFAULT_FILTERS})
            self._jinja_env = env
        return self._jinja_env

    def get_templates_by_collector(self, collector: str, collect_type: str):
        """
        从数据库中查找指定采集器和采集类型的所有配置模板，按 type 分组。

        :param collector: 采集器名称
        :param collect_type: 采集类型
        :return: 字典，key 为 type，value 为该 type 下的所有模板列表
        """
        plugin_id = self.data.get("monitor_plugin_id")
        template_filter = (
            MonitorPluginConfigTemplate.objects.filter(plugin_id=plugin_id)
            if plugin_id
            else MonitorPluginConfigTemplate.objects.filter(
                plugin__collector=collector,
                plugin__collect_type=collect_type,
                plugin__template_type="builtin",
            )
        )
        templates = template_filter.values("type", "config_type", "file_type", "content")

        # 按 type 分组
        templates_by_type = {}
        for template in templates:
            type_name = template["type"]
            if type_name not in templates_by_type:
                templates_by_type[type_name] = []
            templates_by_type[type_name].append(template)

        return templates_by_type

    def render_template(self, template_content: str, context: dict, escape_toml_strings: bool = False):
        """
        渲染模板内容。

        :param template_content: 模板内容字符串
        :param context: 用于模板渲染的变量字典
        :return: 渲染后的配置字符串
        :raises ValueError: 当 instance_id 格式不正确时
        """
        _context = _normalize_template_context(context)

        # 优先使用显式 logical_instance_value（已规范化的逻辑实例值）。
        # 仅在缺失时才尝试解析 instance_id，保持向后兼容。
        logical_instance_value = _context.get("logical_instance_value")
        if logical_instance_value:
            _context["instance_id"] = logical_instance_value
        else:
            instance_id = _context.get("instance_id")
            if instance_id:
                try:
                    if isinstance(instance_id, str):
                        parsed_id = parse_instance_id(instance_id)
                        if parsed_id:
                            _context.update(instance_id=parsed_id[0])
                        else:
                            raise ValueError(f"无效的 instance_id 格式: {instance_id}")
                    elif isinstance(instance_id, (list, tuple)) and len(instance_id) > 0:
                        _context.update(instance_id=instance_id[0])
                except ValueError:
                    raise
                except Exception as e:
                    logger.error(f"解析 instance_id 失败: {instance_id}, 错误: {e}")
                    raise ValueError(f"无效的 instance_id 格式: {instance_id}") from e

        from apps.monitor.utils.snmp_ifmib_capability import is_ifmib_capable_render_context
        from apps.monitor.utils.snmp_interface_template import (
            ensure_core_network_ifmib_jinja,
            ensure_public_ifmib_input_tagexclude,
            ensure_snmp_interface_filter_jinja,
            isolate_snmp_interface_tagpass,
            merge_page_snmp_interface_filters,
            needs_snmp_interface_filter_jinja,
            validate_rendered_core_network_ifmib,
        )

        template_content = ensure_core_network_ifmib_jinja(template_content, _context)
        # 接口过滤与公共 IF-MIB 同能力边界：非 Network Device（如 hardware_server）
        # 即使模板含 ifDescr，也不得静默注入默认 ifType 排除。
        if is_ifmib_capable_render_context(_context) and needs_snmp_interface_filter_jinja(template_content):
            template_content = ensure_snmp_interface_filter_jinja(template_content)

        safe_context = sanitize_template_context(_context)
        if escape_toml_strings:
            safe_context = _escape_toml_context_strings(safe_context)
        try:
            allowed_variables = set(safe_context.keys()) | _MONITOR_TEMPLATE_ALLOWED_VARIABLES
            validate_template_variables(template_content, self.jinja_env, allowed_variables)
        except TemplateSecurityError as e:
            logger.warning(f"采集模板变量校验失败: {e}")
            raise BaseAppException(f"采集模板包含未授权变量: {e}") from e

        template = self.jinja_env.from_string(template_content)
        rendered_template = template.render(safe_context)
        rendered_template = isolate_snmp_interface_tagpass(rendered_template, _context)
        # #4715 跳过与无 marker 用户段同 kind 的 Jinja 后，必须把页面过滤合并回 owner。
        rendered_template = merge_page_snmp_interface_filters(rendered_template, _context)
        # Jinja 不能在 table.field 后裸写 tagexclude（会绑到 field）；渲染后补到 input 级。
        rendered_template = ensure_public_ifmib_input_tagexclude(rendered_template, _context)
        validate_rendered_core_network_ifmib(rendered_template, _context)
        return rendered_template

    def format_configs(self):
        """
        格式化配置数据，将实例和配置合并成最终的配置列表。

        :return: 格式化后的配置列表
        :raises KeyError: 当必需的字段缺失时
        """
        try:
            collect_type = self.data["collect_type"]
            collector = self.data["collector"]
            instances = self.data.get("instances", [])
            configs_template = self.data.get("configs", [])
        except KeyError as e:
            logger.error(f"缺少必需的字段: {e}")
            raise ValueError(f"输入数据缺少必需的字段: {e}") from e

        configs = []
        # 修复：避免修改原始数据，使用副本
        for instance in instances:
            # 创建副本，避免修改原始数据
            instance_copy = {**instance}
            node_ids = instance_copy.pop("node_ids", [])

            if not node_ids:
                logger.warning(f"实例 {instance_copy.get('instance_id', 'unknown')} 没有关联节点")
                continue

            for node_id in node_ids:
                node_info = {"node_id": node_id}
                for config in configs_template:
                    _config = {
                        "collector": collector,
                        "collect_type": collect_type,
                        **node_info,
                        **config,
                        **instance_copy,
                    }
                    if collect_type == "web":
                        _config = normalize_website_request_config(_config)
                    if _is_rabbitmq_collect_config(_config) and _config.get("url") not in (None, ""):
                        _config["url"] = normalize_rabbitmq_management_url(_config.get("url"))
                    configs.append(_config)

        return configs

    def controller(self):  # noqa: C901
        """
        创建采集配置的控制器方法

        优化点：
        1. 使用 batch_create_configs_and_child_configs 原子性创建配置和子配置
        2. 移除手动回滚逻辑，依赖外层事务自动回滚
        3. 简化错误处理
        4. 从数据库读取模板而不是从目录扫描
        5. 提前批量查询模板，避免循环中重复查询数据库
        6. 复用 Jinja2 Environment 对象
        7. 避免修改原始数据
        8. 增强输入验证和错误处理

        :raises ValueError: 当输入数据不合法时
        """
        # 输入验证
        if not self.data:
            raise ValueError("输入数据不能为空")

        try:
            collector = self.data["collector"]
            collect_type = self.data["collect_type"]
        except KeyError as e:
            logger.error(f"输入数据缺少必需字段: {e}")
            raise ValueError(f"输入数据缺少必需字段: {e}") from e

        plugin_id = self.data.get("monitor_plugin_id")
        plugin_template_id = None
        plugin_obj = None
        if plugin_id:
            plugin_obj = MonitorPlugin.objects.filter(id=plugin_id).prefetch_related("monitor_object").first()
            if plugin_obj:
                plugin_template_id = plugin_obj.template_id
        configs = self.format_configs()
        node_configs, node_child_configs, collect_configs = [], [], []

        templates_by_type = self.get_templates_by_collector(collector, collect_type)

        if not templates_by_type:
            logger.warning(f"未找到任何模板：collector={collector}, collect_type={collect_type}")
            raise BaseAppException(f"未找到采集模板：collector={collector}, collect_type={collect_type}")

        if not configs:
            logger.debug(f"没有需要创建的配置：collector={collector}, collect_type={collect_type}")
            raise BaseAppException(f"没有可创建的采集配置：collector={collector}, collect_type={collect_type}")

        for config_info in configs:
            type_name = config_info.get("type")
            if not type_name:
                logger.warning(f"配置缺少 type 字段: {config_info}")
                raise BaseAppException("采集配置缺少 type 字段")

            templates = templates_by_type.get(type_name)

            if not templates:
                logger.warning(f"未找到模板：collector={collector}, collect_type={collect_type}, type={type_name}")
                raise BaseAppException(f"未找到采集模板：collector={collector}, collect_type={collect_type}, type={type_name}")

            if str(collect_type or "") == "exporter" and str(type_name or "").lower() == "kafka":
                from apps.monitor.utils.kafka_sasl import ensure_kafka_sasl_mechanism_defaults

                ensure_kafka_sasl_mechanism_defaults(config_info)

            env_config = {k[4:]: v for k, v in config_info.items() if k.startswith("ENV_")}

            for template in templates:
                is_child = template["config_type"] == "child"
                collector_name = "Telegraf" if is_child else collector
                config_id = str(uuid.uuid4().hex)

                try:
                    render_context = {
                        **config_info,
                        "config_id": config_id.upper(),
                        "plugin_id": plugin_template_id or plugin_id,
                        "monitor_plugin_id": plugin_id,
                    }
                    from apps.monitor.utils.snmp_ifmib_capability import is_ifmib_capable_plugin

                    render_context["ifmib_capable"] = is_ifmib_capable_plugin(plugin_obj)
                    if render_context["ifmib_capable"]:
                        # IF-MIB 是本次下发选项。接入页默认启用；用户可以只对当前
                        # 新实例关闭，已下发实例的 TOML 快照不会受影响。
                        render_context.setdefault("enable_ifmib", True)
                        # 默认 ifType 排除仅对具备过滤 UI 的 Network Device 注入，
                        # 避免 hardware_server 等无开关对象静默丢接口。
                        if "iftype_exclude" not in render_context:
                            from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE

                            render_context["iftype_exclude"] = list(DEFAULT_IFTYPE_EXCLUDE)
                    # 与 IF-MIB 能力判定一致：覆盖 snmp / snmp_h3c 等厂商 collect_type。
                    snmp_collect = str(collect_type or "").startswith("snmp")
                    if snmp_collect and is_child:
                        from apps.monitor.utils.snmp_interface_filters import assert_snmp_interface_filter_mutex_from_values

                        # 互斥校验放在模板渲染前，避免被包装成「渲染采集模板失败」
                        assert_snmp_interface_filter_mutex_from_values(render_context)
                    if is_child and str(collect_type or "") == "exporter" and str(type_name or "").lower() == "kafka":
                        from apps.monitor.utils.kafka_collect_timeouts import assert_kafka_group_metrics_timeout_lt_interval

                        assert_kafka_group_metrics_timeout_lt_interval(
                            config_info.get("ENV_GROUP_METRICS_TIMEOUT") or env_config.get("GROUP_METRICS_TIMEOUT"),
                            config_info.get("interval"),
                        )
                    template_config = self.render_template(
                        template["content"],
                        render_context,
                        escape_toml_strings=template["file_type"] == "toml",
                    )
                except ValidationAppException:
                    raise
                except ValueError as e:
                    raw_id = config_info.get("instance_id")
                    logical_id = config_info.get("logical_instance_value")
                    storage_id = config_info.get("storage_instance_key")
                    logger.error(f"实例识别失败：type={type_name}, raw={raw_id}, logical={logical_id}, storage={storage_id}, 错误: {e}")
                    raise BaseAppException(f"实例识别失败：type={type_name}, instance_id={raw_id}") from e
                except Exception as e:
                    logger.error(f"渲染模板失败：type={type_name}, config_id={config_id}, instance_id={config_info.get('instance_id')}, 错误: {e}")
                    raise BaseAppException(f"渲染采集模板失败：type={type_name}, instance_id={config_info.get('instance_id')}") from e

                if is_child:
                    child_env_config = {f"{k.upper()}__{config_id.upper()}": v for k, v in env_config.items()}
                    node_child_configs.append(
                        dict(
                            id=config_id,
                            collect_type=collect_type,
                            type=config_info["type"],
                            content=template_config,
                            node_id=config_info["node_id"],
                            collector_name=collector_name,
                            env_config=child_env_config,
                        )
                    )
                else:
                    node_configs.append(
                        dict(
                            id=config_id,
                            name=f"{collector_name}-{config_id}",
                            content=template_config,
                            node_id=config_info["node_id"],
                            collector_name=collector_name,
                            env_config=env_config,
                        )
                    )

                collect_configs.append(
                    CollectConfig(
                        id=config_id,
                        collector=collector_name,
                        monitor_instance_id=config_info["instance_id"],
                        monitor_plugin_id=plugin_id,
                        collect_type=collect_type,
                        config_type=config_info["type"],
                        file_type=template["file_type"],
                        is_child=is_child,
                    )
                )

        if not collect_configs:
            logger.warning(f"没有生成任何配置：collector={collector}, collect_type={collect_type}")
            raise BaseAppException(f"没有生成任何采集配置：collector={collector}, collect_type={collect_type}")

        # 步骤2：批量创建 CollectConfig（使用外层事务，不新建事务）
        try:
            CollectConfig.objects.bulk_create(collect_configs, batch_size=DatabaseConstants.COLLECT_CONFIG_BATCH_SIZE)
            logger.info(f"创建 CollectConfig 成功，数量={len(collect_configs)}")
        except Exception as e:
            logger.error(f"批量创建 CollectConfig 失败：{e}")
            raise

        # 必须本进程写入：Controller 常处于外层 atomic（节点推送还会锁 Node 行）。
        # 再 NATS 到另一连接写 NodeCollectorConfiguration 会与父行锁自死锁。
        if node_configs or node_child_configs:
            try:
                NodeMgmt(is_local_client=True).batch_create_configs_and_child_configs(node_configs, node_child_configs)
                logger.info(f"创建配置成功，node_config={len(node_configs)}个，child_config={len(node_child_configs)}个")
            except Exception as e:
                logger.error(f"本进程写入采集配置失败：node_configs={len(node_configs)}, child_configs={len(node_child_configs)}, 错误: {e}")
                raise

        logger.info(f"创建采集配置成功，共{len(collect_configs)}个配置")
