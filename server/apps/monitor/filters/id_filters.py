"""Filter helpers that keep non-integer IDs out of ORM lookups."""


def filter_positive_int_field(queryset, field_name: str, value):
    """Apply an exact filter on an integer / FK-id field.

    Empty values leave the queryset unchanged. Non-digit strings (e.g. a
    monitor-object *type* id like ``Network Device`` mistakenly sent as
    ``monitor_object_id``) must not reach the ORM — Django raises
    ``ValueError`` and the API returns 500.
    """
    if value in (None, ""):
        return queryset
    value_str = str(value).strip()
    if not value_str or not value_str.isdigit():
        return queryset.none()
    return queryset.filter(**{field_name: value_str})
