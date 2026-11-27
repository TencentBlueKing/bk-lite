LAYOUT_TYPES = {"section", "tab"}
TABLE_TYPES = {"table", "nestedTable", "task", "cab"}
READ_ONLY = {"read", "readonly", "hidden", "disabled"}
TICKET_SPECIFIC = {"attachment", "signature", "subProcessForm", "calculate"}


def reusable_value(value):
    if isinstance(value, dict):
        return {key: reusable_value(item) for key, item in value.items() if isinstance(key, str) and not key.startswith("_")}
    if isinstance(value, list):
        return [reusable_value(item) for item in value]
    return value


def project_template_values(fields, values, permissions, inherited="edit"):
    if not isinstance(values, dict):
        return {}
    result = {}
    for field in fields:
        key = field.get("key")
        if not isinstance(key, str) or key.startswith("_"):
            continue
        mode = permissions.get(key, permissions.get("*", "edit"))
        if (
            inherited in READ_ONLY
            or mode in READ_ONLY
            or field.get("state") in READ_ONLY
            or field.get("fetch")
            or field.get("type") in TICKET_SPECIFIC
        ):
            continue
        if field.get("type") in TABLE_TYPES:
            rows = values.get(key)
            if isinstance(rows, list):
                result[key] = [project_template_values(field.get("children") or [], row, permissions, mode) for row in rows if isinstance(row, dict)][
                    :100
                ]
        elif field.get("children") and field.get("type") in LAYOUT_TYPES:
            result.update(project_template_values(field["children"], values, permissions, mode))
        elif key in values and not field.get("fetch"):
            result[key] = reusable_value(values[key])
    return result
