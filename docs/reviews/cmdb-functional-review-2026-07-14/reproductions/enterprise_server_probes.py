#!/usr/bin/env python
"""F65/F68 只读复现；不写数据库或生产文件。"""

import argparse
import inspect
import time

import django


django.setup()


def probe_f65():
    from apps.cmdb_enterprise.collect.remaining_node_params import GenericProtocolNodeParamsMixin
    from apps.cmdb_enterprise.collect.tree import ENTERPRISE_COLLECT_OBJ_TREE

    children = []
    for group in ENTERPRISE_COLLECT_OBJ_TREE:
        value = group["children"]
        children.extend(value if isinstance(value, list) else [value])
    accepted = [
        field
        for field in ("token", "access_key", "secret_key", "community")
        if field in inspect.getsource(GenericProtocolNodeParamsMixin._build_credential_payload)
    ]
    encrypted = sorted({field for child in children for field in child.get("encrypted_fields", [])})
    print({"objects": len(children), "encrypted_fields": encrypted, "accepted_secret_fields": sorted(accepted)})


def probe_f68():
    from apps.cmdb_enterprise.collect.nacos import NacosCollectionPlugin

    class FakeInst:
        model_id = "nacos"
        instances = [{"inst_name": "nacos-probe"}]

    NacosCollectionPlugin.get_collect_inst = lambda self: FakeInst()
    runner = NacosCollectionPlugin(inst_name="nacos-probe", inst_id=1, task_id=1)
    now = int(time.time())
    rows = [
        {
            "metric": {"__name__": "nacos_info_gauge", "collect_status": "success", "ip_addr": "old"},
            "value": [now - 172800, "1"],
        },
        {
            "metric": {"__name__": "nacos_info_gauge", "collect_status": "success", "ip_addr": "fresh"},
            "value": [now, "1"],
        },
    ]
    runner.format_data({"result": rows})
    runner.format_metrics()
    print(runner.result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=("f65", "f68"))
    args = parser.parse_args()
    {"f65": probe_f65, "f68": probe_f68}[args.probe]()
