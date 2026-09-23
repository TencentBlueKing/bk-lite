"""数据集版本归档写在 description 上的语言无关标记。"""

ARCHIVE_DESCRIPTION_PREFIX = "[archived] "
LEGACY_ARCHIVE_DESCRIPTION_PREFIXES = (ARCHIVE_DESCRIPTION_PREFIX, "[已归档] ")


def with_archive_description(description: str | None) -> str:
    text = description or ""
    for prefix in LEGACY_ARCHIVE_DESCRIPTION_PREFIXES:
        if text.startswith(prefix):
            return text
    return f"{ARCHIVE_DESCRIPTION_PREFIX}{text}"


def without_archive_description(description: str | None) -> str:
    text = description or ""
    for prefix in LEGACY_ARCHIVE_DESCRIPTION_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text
