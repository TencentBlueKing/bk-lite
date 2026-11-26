#!/usr/bin/env python3
"""在执行机发现当前账号可见资源，或导出管理员选定的无密 ITSM 目录。"""

import argparse
import json
import ssl
import sys
from pathlib import Path


def read_inventory(content, object_types):
    result = {}
    for kind, vm_type in object_types.items():
        view = content.viewManager.CreateContainerView(content.rootFolder, [vm_type], True)
        try:
            rows = []
            for obj in view.view:
                if kind == "template" and not (obj.config and obj.config.template):
                    continue
                if kind == "datastore" and not obj.summary.accessible:
                    continue
                rows.append({"value": obj._moId, "label": obj.name})
            result[kind] = sorted(rows, key=lambda row: (row["label"], row["value"]))
        finally:
            view.Destroy()
    return result


def export_catalog(profile, inventory, target_id, vc_instance_uuid, max_quantity):
    catalog = profile["catalog"]
    discovered = {kind: {row["value"] for row in rows} for kind, rows in inventory.items()}
    if profile["folder_id"] not in discovered["folder"] or profile["resource_pool_id"] not in discovered["resource_pool"]:
        raise ValueError("目标文件夹或资源池不可见")
    for kind, field in (("template", "value"), ("network", "value"), ("disk_policy", "datastore_id")):
        known = discovered["datastore" if kind == "disk_policy" else kind]
        if any(row[field] not in known for row in catalog[kind]):
            raise ValueError("授权目录包含已不可用的资源")
    public_keys = {
        "flavor": ("value", "label", "cpu", "memory_gib"),
        "template": ("value", "label"),
        "network": ("value", "label"),
        "disk_policy": ("value", "label", "datastore_id", "allowed_disk_gib"),
    }
    return {
        "vc_instance_uuid": vc_instance_uuid,
        "vc_host": profile["host"],
        "target_id": target_id,
        "max_quantity": max_quantity,
        "catalog": {kind: [{key: row[key] for key in keys} for row in catalog[kind]] for kind, keys in public_keys.items()},
    }


def main():
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("profile", type=Path, help="执行机上的 vCenter profile JSON 路径")
    cli.add_argument("--export", action="store_true", help="核对 profile 已批准资源并导出 ITSM 可绑定的无密目录")
    cli.add_argument("--vc-instance-uuid", help="CMDB 的 vCenter 根资产 UUID")
    cli.add_argument("--target-id", type=int, help="BK-Lite 作业执行机 ID")
    cli.add_argument("--max-quantity", type=int, default=1, help="审批一次允许创建的最大台数")
    args = cli.parse_args()
    if args.export and not (args.vc_instance_uuid and args.target_id and args.target_id > 0 and 1 <= args.max_quantity <= 100):
        cli.error("导出需要指定 CMDB 根资产、作业执行机和有效台数")
    profile = json.loads(args.profile.read_text())
    pwd_file = Path(profile["password_file"])
    if pwd_file.stat().st_mode & 0o077:
        raise PermissionError("凭据文件权限过宽")
    connection = SmartConnect(
        host=profile["host"],
        port=profile.get("port", 443),
        user=profile["username"],
        pwd=pwd_file.read_text().rstrip("\r\n"),
        sslContext=ssl.create_default_context(cafile=profile.get("ca_file")),
        httpConnectionTimeout=30,
    )
    try:
        inventory = read_inventory(
            connection.content,
            {
                "template": vim.VirtualMachine,
                "network": vim.Network,
                "datastore": vim.Datastore,
                "folder": vim.Folder,
                "resource_pool": vim.ResourcePool,
            },
        )
        result = export_catalog(profile, inventory, args.target_id, args.vc_instance_uuid, args.max_quantity) if args.export else inventory
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        Disconnect(connection)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - SDK 故障正文可能包含连接信息
        print(f"资源目录核对失败（{type(exc).__name__}）", file=sys.stderr)
        sys.exit(1)
