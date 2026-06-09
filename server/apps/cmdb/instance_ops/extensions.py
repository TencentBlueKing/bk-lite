"""实例能力域的企业版扩展契约（社区侧门面）。

社区默认实现为空契约：文件字段不做任何处理，上传/下载/临时删除接口返回
「未启用」。企业版通过
``apps.cmdb.enterprise.instance_ops.provider.get_instance_enterprise_extension``
返回携带附件/图片真实逻辑的子类实例。
"""

from apps.core.exceptions.base_app_exception import BaseAppException

from apps.cmdb.extensions import registry

ENTERPRISE_DISABLED_MESSAGE = "附件/图片功能未启用（企业版）"


class InstanceEnterpriseExtension:
    """实例能力域扩展契约。社区默认全部为 no-op / 未启用。"""

    # ---- 写路径：实例增改/删除时的文件字段处理 ----

    def normalize_file_fields(
        self,
        model_id: str,
        instance_data: dict,
        attrs: list,
        *,
        operator: str,
        old_instance: dict | None = None,
    ) -> dict:
        """校验并规范化实例数据中的附件/图片字段。默认原样返回。

        企业版在此校验数量/大小/类型、将台账 pending→committed、把移除的
        文件标 orphaned，并把字段值规范化为元数据 JSON 数组。
        """
        return instance_data

    def commit_instance_files(self, model_id: str, inst_id, saved_instance: dict, attrs: list, *, operator: str) -> None:
        """实例保存后落账：引用文件转 committed 并补 inst_id、移除文件标 orphaned。默认 no-op。"""
        return None

    def on_instance_delete(self, model_id: str, inst_id, instance: dict) -> None:
        """实例删除后回调，企业版据此把该实例的文件标记为 orphaned。默认 no-op。"""
        return None

    # ---- 接口：上传/下载/临时删除（社区 view 委托，默认未启用） ----

    def handle_upload(self, *, request, model_id: str, attr_id: str, uploaded_file):
        raise BaseAppException(ENTERPRISE_DISABLED_MESSAGE)

    def handle_download(self, *, request, file_id: str, check_read_permission=None):
        raise BaseAppException(ENTERPRISE_DISABLED_MESSAGE)

    def handle_delete_temp(self, *, request, file_id: str):
        raise BaseAppException(ENTERPRISE_DISABLED_MESSAGE)


_EMPTY_INSTANCE_EXTENSION = InstanceEnterpriseExtension()


def get_instance_enterprise_extension() -> InstanceEnterpriseExtension:
    return registry.get("instance_ops", _EMPTY_INSTANCE_EXTENSION)
