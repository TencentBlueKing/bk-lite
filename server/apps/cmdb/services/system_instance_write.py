"""CMDB 系统写入：周期任务写台账时显式携带组织范围。"""


def system_create_or_update(model_id: str, instance_info: dict, existing_id=None, organization=None) -> dict:
    """已有 _id 走 update，否则 create。统一 system 操作员，并传入 allowed_org_ids。"""
    from apps.cmdb.services.instance import InstanceManage

    allowed_org_ids = organization or []
    if existing_id:
        InstanceManage.instance_update(
            [],
            [],
            existing_id,
            instance_info,
            "system",
            skip_permission_check=True,
            allowed_org_ids=allowed_org_ids,
            record_change=False,
        )
        return {"_id": existing_id, **instance_info}
    created = InstanceManage.instance_create(
        model_id,
        instance_info,
        "system",
        allowed_org_ids=allowed_org_ids,
        record_change=False,
    )
    return {"_id": created["_id"], **instance_info}
