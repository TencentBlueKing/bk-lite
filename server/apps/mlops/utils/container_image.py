"""容器镜像引用格式校验。"""

import re

_DOMAIN_COMPONENT = r"(?:[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9])"
_DOMAIN = rf"{_DOMAIN_COMPONENT}(?:\.{_DOMAIN_COMPONENT})*"
_REGISTRY = rf"{_DOMAIN}(?::[0-9]+)?"
_PATH_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
_NAME = rf"(?:(?:{_REGISTRY})/)?{_PATH_COMPONENT}(?:/{_PATH_COMPONENT})*"
_TAG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}"
_DIGEST_ALGORITHM = r"[A-Za-z][A-Za-z0-9]*(?:[+._-][A-Za-z][A-Za-z0-9]*)*"
_DIGEST = rf"{_DIGEST_ALGORITHM}:[0-9A-Fa-f]{{32,}}"
_CONTAINER_IMAGE_REFERENCE = re.compile(
    rf"{_NAME}(?::{_TAG})?(?:@{_DIGEST})?\Z",
    re.ASCII,
)


def is_valid_container_image_reference(value: str) -> bool:
    """判断字符串是否为单行 OCI/Docker 风格镜像引用。"""
    return isinstance(value, str) and 0 < len(value) <= 255 and _CONTAINER_IMAGE_REFERENCE.fullmatch(value) is not None
