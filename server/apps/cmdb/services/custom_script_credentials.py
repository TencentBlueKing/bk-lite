# -- coding: utf-8 --
"""自定义脚本任务的传输凭据字段。登录凭据走主机 SSH / WinRM，不再声明业务凭据。"""

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin

TRANSPORT_ENCRYPTED_FIELDS = ("password", "private_key", "passphrase")


def transport_encrypted_fields():
    return list(TRANSPORT_ENCRYPTED_FIELDS)


def load_plugin(plugin_pk):
    if not plugin_pk:
        return None
    return CustomCollectPlugin.objects.filter(id=plugin_pk).first()


def task_is_custom_script(instance):
    return getattr(instance, "task_type", None) == CollectPluginTypes.CUSTOM_SCRIPT
