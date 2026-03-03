from typing import Mapping, Any


def parse_page_params(
    params: Mapping[str, Any],
    default_page: int = 1,
    default_page_size: int = 10,
    allow_page_size_all: bool = False,
) -> tuple[int, int]:
    """解析分页参数，防止非法值导致接口抛出 500。"""
    try:
        page = int(params.get("page", default_page))
    except (ValueError, TypeError):
        page = default_page

    try:
        page_size = int(params.get("page_size", default_page_size))
    except (ValueError, TypeError):
        page_size = default_page_size

    if page < 1:
        page = default_page

    if allow_page_size_all and page_size == -1:
        return page, page_size

    if page_size < 1:
        page_size = default_page_size

    return page, page_size