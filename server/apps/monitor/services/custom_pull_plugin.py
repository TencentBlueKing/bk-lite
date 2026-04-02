import copy

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate


DEFAULT_PULL_UI_TEMPLATE = {
    "object_name": "",
    "instance_type": "",
    "collect_type": "bkpull",
    "config_type": ["custom_pull"],
    "collector": "Telegraf",
    "instance_id": "{{cloud_region}}_{{server_url}}",
    "form_fields": [
        {
            "name": "auth_type",
            "label": "认证",
            "type": "select",
            "required": True,
            "default_value": "none",
            "options": [
                {"label": "无", "value": "none"},
                {"label": "Basic Auth", "value": "basic"},
                {"label": "Bearer Token", "value": "bearer"},
            ],
            "description": "目标端点需要认证时选择对应方式",
            "transform_on_edit": {
                "origin_path": "child.content.config.http_headers.X-BK-Auth-Type",
                "to_api": {},
            },
            "widget_props": {"placeholder": "请选择认证方式"},
        },
        {
            "name": "username",
            "label": "用户名",
            "type": "input",
            "required": True,
            "visible_in": "both",
            "dependency": {"field": "auth_type", "value": "basic"},
            "description": "Basic Auth 用户名",
            "widget_props": {"placeholder": "用户名"},
            "transform_on_edit": {
                "origin_path": "child.content.config.username",
                "to_api": {},
            },
        },
        {
            "name": "ENV_PASSWORD",
            "label": "密码",
            "type": "password",
            "required": True,
            "encrypted": True,
            "visible_in": "both",
            "dependency": {"field": "auth_type", "value": "basic"},
            "description": "Basic Auth 密码",
            "widget_props": {"placeholder": "密码"},
            "transform_on_edit": {
                "origin_path": "child.env_config.PASSWORD__{{config_id}}",
                "to_api": {},
            },
        },
        {
            "name": "ENV_BEARER_TOKEN",
            "label": "Token",
            "type": "password",
            "required": True,
            "encrypted": True,
            "visible_in": "both",
            "dependency": {"field": "auth_type", "value": "bearer"},
            "description": "Bearer Token 认证令牌",
            "widget_props": {"placeholder": "请输入 Token"},
            "transform_on_edit": {
                "origin_path": "child.env_config.BEARER_TOKEN__{{config_id}}",
                "to_api": {},
            },
        },
        {
            "name": "interval",
            "label": "采集间隔",
            "type": "inputNumber",
            "required": True,
            "default_value": 10,
            "description": "监控数据的采集时间间隔（单位：秒）",
            "widget_props": {"min": 1, "precision": 0, "placeholder": "间隔", "addonAfter": "s"},
            "transform_on_edit": {
                "origin_path": "child.content.config.interval",
                "to_form": {"regex": "^(\\d+)s$"},
                "to_api": {"suffix": "s"},
            },
        },
    ],
    "table_columns": [
        {
            "name": "node_ids",
            "label": "节点",
            "type": "select",
            "required": True,
            "widget_props": {"placeholder": "请选择节点"},
            "enable_row_filter": True,
        },
        {
            "name": "server_url",
            "label": "服务地址",
            "type": "input",
            "required": True,
            "widget_props": {"placeholder": "请输入完整服务地址，例如 http://127.0.0.1:9090/metrics"},
            "change_handler": {
                "type": "simple",
                "source_fields": ["server_url"],
                "target_field": "instance_name",
            },
        },
        {
            "name": "instance_name",
            "label": "实例名称",
            "type": "input",
            "required": True,
            "widget_props": {"placeholder": "实例名称"},
            "is_only": True,
        },
        {
            "name": "group_ids",
            "label": "组",
            "type": "group_select",
            "required": False,
            "widget_props": {"placeholder": "请选择组"},
        },
    ],
    "extra_edit_fields": {},
}


DEFAULT_PULL_CHILD_TEMPLATE = """[[inputs.prometheus]]
    startup_error_behavior = "retry"
    urls = ["{{ server_url }}"]
    interval = "{{ interval }}s"
    timeout = "{{ interval }}s"
    response_timeout = "{{ interval }}s"
{% if username %}
    username = "{{ username }}"
{% endif %}
{% if ENV_PASSWORD %}
    password = "${PASSWORD__{{ config_id }}}"
{% endif %}
{% if ENV_BEARER_TOKEN %}
    bearer_token = "${BEARER_TOKEN__{{ config_id }}}"
{% endif %}
    insecure_skip_verify = true
    [inputs.prometheus.http_headers]
        X-BK-Auth-Type = "{{ auth_type | default('none', true) }}"
    [inputs.prometheus.tags]
        instance_id = "{{ instance_id }}"
        instance_type = "{{ instance_type }}"
        collect_type = "bkpull"
        config_type = "custom_pull"
        plugin_id = "{{ plugin_id }}"
"""


class CustomPullPluginService:
    @staticmethod
    def initialize_templates(plugin: MonitorPlugin):
        monitor_object = plugin.monitor_object.all().order_by("id").first()
        if monitor_object is None:
            raise BaseAppException("自定义PULL模板必须绑定一个监控对象")

        ui_template = copy.deepcopy(DEFAULT_PULL_UI_TEMPLATE)
        ui_template["object_name"] = monitor_object.name
        ui_template["instance_type"] = monitor_object.name

        with transaction.atomic():
            MonitorPluginConfigTemplate.objects.update_or_create(
                plugin=plugin,
                type="custom_pull",
                config_type="child",
                file_type="toml",
                defaults={"content": DEFAULT_PULL_CHILD_TEMPLATE},
            )
            MonitorPluginUITemplate.objects.update_or_create(
                plugin=plugin,
                defaults={"content": ui_template},
            )
