import json


def load_json(monitor_object_name, encoding="utf-8"):

    file_path = f"apps/monitor/policy_template/files/{monitor_object_name}.json"
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return json.load(f)
    except Exception:
        return []
