"""内置数据源稳定身份与升级认领。

首次升级只按精确身份认领，禁止「仅按 rest_api 唯一行」兜底，
避免同接口的用户自定义数据源被误标为内置后进入物理删除。
"""


def legacy_name_from_stable_key(stable_key, rest_api):
    """从 `{legacy_name}::{rest_api}` 形态的稳定键解析历史展示名。"""
    if not stable_key or not rest_api:
        return None
    suffix = f"::{rest_api}"
    if not stable_key.endswith(suffix):
        return None
    legacy_name = stable_key[: -len(suffix)]
    return legacy_name or None


def find_claimable_datasource(model, *, stable_key, name, rest_api):
    """
    按稳定身份查找可认领的数据源行。

    顺序：
    1. build_in_key
    2. 精确 (当前 name, rest_api)
    3. 精确 (stable_key 中的历史名, rest_api) —— 本轮改展示名用
    """
    by_key = model.objects.filter(build_in_key=stable_key).first()
    by_identity = model.objects.filter(name=name, rest_api=rest_api).first()
    by_legacy_identity = None
    if not by_key and not by_identity:
        legacy_name = legacy_name_from_stable_key(stable_key, rest_api)
        if legacy_name and legacy_name != name:
            by_legacy_identity = model.objects.filter(name=legacy_name, rest_api=rest_api).first()

    candidates = [item for item in (by_key, by_identity, by_legacy_identity) if item is not None]
    if len({item.pk for item in candidates}) > 1:
        raise ValueError(f"内置数据源唯一键冲突: {stable_key}")

    instance = by_key or by_identity or by_legacy_identity
    if instance is None:
        return None
    if instance.build_in_key not in (None, "", stable_key):
        raise ValueError(f"内置数据源唯一键冲突: {stable_key}")
    return instance
