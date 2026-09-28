"""导出当前目录供真实前端页面参数测试使用，不访问设备或业务数据。"""

import argparse
import json
import os
from pathlib import Path

import django


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    django.setup()

    from apps.cmdb.extensions import registry
    from apps.cmdb.services.collect_object_tree import get_collect_obj_tree
    from apps.cmdb.services.collect_vault_binding import binding_for_collect_object
    from apps.cmdb_enterprise.collect.provider import get_collect_enterprise_extension

    registry.register("collect", get_collect_enterprise_extension())
    entries = []
    for group in get_collect_obj_tree():
        for child in group.get("children", []):
            child = dict(child)
            child["binding"] = binding_for_collect_object(
                child["id"], model_id=child["model_id"], driver_type=child["type"], protocol=child.get("credential_protocol")
            )
            entries.append(child)
    args.output.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
