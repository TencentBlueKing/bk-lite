import unicodedata


def normalize_identity(value: str | None) -> str:
    """统一 APM 身份字段；保留大小写，只折叠 Unicode 表示与首尾空白。"""
    return unicodedata.normalize("NFKC", value or "").strip()


def normalize_service_identity(namespace: str | None, name: str | None) -> tuple[str, str]:
    normalized_namespace = normalize_identity(namespace)
    normalized_name = normalize_identity(name)
    if not normalized_name:
        raise ValueError("service.name 不能为空")
    return normalized_namespace, normalized_name


def normalize_instance_identity(instance_id: str | None) -> str:
    normalized = normalize_identity(instance_id)
    if not normalized:
        raise ValueError("service.instance.id 不能为空")
    return normalized
