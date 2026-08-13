def normalize_group_ids(values):
    normalized = []
    for value in values or []:
        if value in (None, ""):
            continue
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(normalized))


def is_groups_subset(datasource_groups, connection_groups):
    source = set(normalize_group_ids(datasource_groups))
    connection = set(normalize_group_ids(connection_groups))
    if not source:
        return False
    return source.issubset(connection)


def find_groups_outside_connection(datasource_groups, connection_groups):
    source = set(normalize_group_ids(datasource_groups))
    connection = set(normalize_group_ids(connection_groups))
    return sorted(source - connection)
