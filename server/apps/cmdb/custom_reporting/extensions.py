"""custom_reporting 能力域企业版扩展契约（社区侧门面，默认 no-op）。

社区从不 import 企业实现；商业 overlay 在 ready() 注册实现到注册表 "custom_reporting" 槽位。
"""

from apps.cmdb.extensions import registry
from apps.core.exceptions.base_app_exception import BaseAppException

_NOT_ENABLED = "自定义上报为商业版能力，未启用"


class CustomReportingExtension:
    """自定义上报契约。社区默认全部 no-op（社区版不具备该商业能力）。"""

    def register_model_fields(self, model_id: str, instances: list, username: str = "admin") -> list:
        return []

    def validate_instance_fields(self, model_id: str, instances: list) -> None:
        return None

    def get_declared_attr_ids(self, model_id: str) -> set:
        return set()

    def validate_relation_fields(self, model_id: str, relations: list, identity_keys=None) -> None:
        return None

    def normalize_identity_keys(self, identity_keys) -> list:
        return []

    def bootstrap_model(self, quick_model: dict, team: list, username: str = "admin"):
        return None

    def sync_model_group(self, quick_model: dict, team: list, username: str = "admin"):
        return None

    # ------------------------------------------------------------------
    # HTTP-facing methods (社区 no-op；商业版 overlay 提供真实实现)
    # ------------------------------------------------------------------

    def list_tasks(self, request, params) -> dict:
        return {"count": 0, "next": None, "previous": None, "results": []}

    def get_task(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def create_task(self, request, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def update_task(self, request, task_id, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def delete_task(self, request, task_id) -> None:
        raise BaseAppException(_NOT_ENABLED)

    def get_batch_activity(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def get_onboarding_document(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def issue_credential(self, request, task_id, params) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def rotate_credential(self, request, task_id, credential_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def revoke_credential(self, request, task_id, credential_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def approve_cleanup_review(self, request, task_id, review_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def reject_cleanup_review(self, request, task_id, review_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def ingest(self, request, token, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)


_EMPTY_CUSTOM_REPORTING = CustomReportingExtension()


def get_custom_reporting_extension() -> CustomReportingExtension:
    return registry.get("custom_reporting", _EMPTY_CUSTOM_REPORTING)
