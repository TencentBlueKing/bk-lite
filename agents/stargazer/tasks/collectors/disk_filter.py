from typing import Any


def _parse_fstypes(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value or "").split(",")
    return {str(item).strip().lower() for item in values if str(item).strip()}


def should_collect_disk(
    fstype: Any,
    *,
    include_fstypes: Any = None,
    exclude_fstypes: Any = None,
) -> bool:
    """Return whether a disk passes the configured filesystem-type rules.

    A non-empty include list is an allowlist. The exclude list is always
    evaluated afterwards, so it has priority when a type occurs in both lists.
    """
    normalized_fstype = str(fstype or "").strip().lower()
    includes = _parse_fstypes(include_fstypes)
    excludes = _parse_fstypes(exclude_fstypes)
    return (not includes or normalized_fstype in includes) and normalized_fstype not in excludes
