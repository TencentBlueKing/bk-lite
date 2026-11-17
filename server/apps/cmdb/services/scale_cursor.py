from apps.cmdb.models.scale_cursor import CmdbScaleCursor


def _database_access_blocked(exc: BaseException) -> bool:
    """单测未打开数据库时，游标保持空，同步仍按原来的一次扫完执行。"""
    return "Database access not allowed" in str(exc)


def load_scale_cursor(key: str) -> dict:
    try:
        row = CmdbScaleCursor.objects.filter(key=key).first()
    except Exception as exc:
        if _database_access_blocked(exc):
            return {}
        raise
    if row is None or not isinstance(row.payload, dict):
        return {}
    return dict(row.payload)


def save_scale_cursor(key: str, payload: dict) -> None:
    try:
        CmdbScaleCursor.objects.update_or_create(key=key, defaults={"payload": payload})
    except Exception as exc:
        if _database_access_blocked(exc):
            return
        raise


def clear_scale_cursor(key: str) -> None:
    try:
        CmdbScaleCursor.objects.filter(key=key).delete()
    except Exception as exc:
        if _database_access_blocked(exc):
            return
        raise
