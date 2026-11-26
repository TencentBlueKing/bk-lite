#!/usr/bin/env python3
"""BK-Lite 作业入口：每台虚拟机一个交付编号，在固定执行机上创建或核对。"""

import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import ssl
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def normalize_host(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("vCenter 地址无效")
    host = value.strip().rstrip(".")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        hostname = host.encode("idna").decode("ascii").lower()
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in hostname.split(".")):
            raise ValueError("vCenter 地址无效")
        return hostname


def decode(payload):
    if len(payload) > 8192:
        raise ValueError("交付参数过长")
    req = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
    required = {"vc_host", "delivery_id", "profile", "template_id", "cpu", "memory_gib", "data_disk_gib", "network_id", "disk_policy_id"}
    if not isinstance(req, dict) or req.keys() != required:
        raise ValueError("交付参数不完整或含有未知字段")
    normalize_host(req["vc_host"])
    for key in ("delivery_id", "profile", "template_id", "network_id", "disk_policy_id"):
        if not isinstance(req[key], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", req[key]):
            raise ValueError("交付标识无效")
    for key, minimum in (("cpu", 1), ("memory_gib", 1), ("data_disk_gib", 0)):
        if type(req[key]) is not int or req[key] < minimum:
            raise ValueError("交付规格必须为有效整数")
    return req


@contextmanager
def lock_delivery(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def save_receipt(path, digest, task_id):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        try:
            json.dump({"digest": digest, "task_id": task_id}, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def execute(req, center, journal_dir, timeout):
    if journal_dir.stat().st_mode & 0o022:
        raise PermissionError("交付日志目录只允许作业账号写入")
    digest = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
    key = hashlib.sha256(req["delivery_id"].encode()).hexdigest()
    receipt = journal_dir / (key + ".json")
    with lock_delivery(journal_dir / (key + ".lock")):
        if receipt.exists():
            old = json.loads(receipt.read_text())
            if old["digest"] != digest:
                raise ValueError("同一交付编号的配置已变更")
            task_id = old["task_id"]
        else:
            center.validate(req)
            # 先持久化待核对标记，再向 vCenter 发送克隆。
            save_receipt(receipt, digest, None)
            task_id = center.submit(req)
            save_receipt(receipt, digest, task_id)
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = center.observe(req, task_id)
        except Exception as exc:
            result = {"status": "unconfirmed", "error_type": type(exc).__name__}
        result.update(delivery_id=req["delivery_id"], task_id=task_id)
        if result["status"] != "pending" or time.monotonic() >= deadline:
            return result
        time.sleep(min(5, max(0, deadline - time.monotonic())))


class VCenter:
    def __init__(self, service, profile):
        from pyVmomi import vim

        self.vim = vim
        self.service = service
        self.profile = profile
        self.folder = vim.Folder(profile["folder_id"], service._stub)
        self.pool = vim.ResourcePool(profile["resource_pool_id"], service._stub)

    def validate(self, req):
        catalog = self.profile["catalog"]
        sizes = {(row["cpu"], row["memory_gib"]) for row in catalog["flavor"]}
        if (req["cpu"], req["memory_gib"]) not in sizes or req["template_id"] not in {row["value"] for row in catalog["template"]}:
            raise ValueError("规格或模板不在授权范围")
        disk = next((row for row in catalog["disk_policy"] if row["value"] == req["disk_policy_id"]), None)
        if not disk or req["data_disk_gib"] not in disk["allowed_disk_gib"]:
            raise ValueError("数据盘不在授权范围")
        if req["network_id"] not in {row["value"] for row in catalog["network"]}:
            raise ValueError("网络不在授权范围")
        net_type = self.vim.dvs.DistributedVirtualPortgroup if req["network_id"].startswith("dvportgroup-") else self.vim.Network
        self.network = net_type(req["network_id"], self.service._stub)
        self.store = self.vim.Datastore(disk["datastore_id"], self.service._stub)
        self.template = self.vim.VirtualMachine(req["template_id"], self.service._stub)
        if not self.template.config.template:
            raise ValueError("所选镜像不是虚拟机模板")
        storage = self.store.summary
        if not storage.accessible or storage.freeSpace < req["data_disk_gib"] * 1024**3:
            raise ValueError("数据存储不可访问或空闲空间不足")
        if not any(
            host.runtime.connectionState == "connected"
            and not host.runtime.inMaintenanceMode
            and self.store in host.datastore
            and self.network in host.network
            for host in self.pool.owner.host
        ):
            raise ValueError("资源池无同时可访问目标网络和存储的主机")
        self.clone_spec = self.build_spec(req)
        self.find(req)

    def identity(self, req):
        key = hashlib.sha256((req["profile"] + "/" + req["delivery_id"]).encode()).hexdigest()
        return (
            self.profile.get("name_prefix", "vm") + "-" + key[:12],
            "BK-Lite-ITSM:" + hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest(),
        )

    def find(self, req):
        name, marker = self.identity(req)
        machine = self.service.content.searchIndex.FindChild(entity=self.folder, name=name)
        if machine and (not isinstance(machine, self.vim.VirtualMachine) or machine.config.annotation != marker):
            raise ValueError("目标名称已被其他资源占用")
        return machine

    def build_spec(self, req):
        vim = self.vim
        dev = vim.vm.device
        hardware = self.template.config.hardware.device
        nics = [item for item in hardware if isinstance(item, dev.VirtualEthernetCard)]
        if len(nics) != 1:
            raise ValueError("交付模板需配置一张网卡")
        nic = nics[0]
        if isinstance(self.network, vim.dvs.DistributedVirtualPortgroup):
            port = vim.dvs.PortConnection(switchUuid=self.network.config.distributedVirtualSwitch.uuid, portgroupKey=self.network.key)
            nic.backing = dev.VirtualEthernetCard.DistributedVirtualPortBackingInfo(port=port)
        else:
            nic.backing = dev.VirtualEthernetCard.NetworkBackingInfo(network=self.network, deviceName=self.network.name)
        changes = [dev.VirtualDeviceSpec(operation="edit", device=nic)]
        if req["data_disk_gib"]:
            controllers = [item for item in hardware if isinstance(item, dev.VirtualSCSIController)]
            slots = ((c.key, i) for c in controllers for i in range(16) if i != c.scsiCtlrUnitNumber)
            occupied = {(item.controllerKey, item.unitNumber) for item in hardware}
            slot = next((s for s in slots if s not in occupied), None)
            if slot is None:
                raise ValueError("模板缺少可用 SCSI 插槽")
            backing = dev.VirtualDisk.FlatVer2BackingInfo(fileName="", diskMode="persistent", thinProvisioned=True, datastore=self.store)
            disk = dev.VirtualDisk(
                key=-100, controllerKey=slot[0], unitNumber=slot[1], backing=backing, capacityInKB=req["data_disk_gib"] * 1024**2
            )
            changes.append(dev.VirtualDeviceSpec(operation="add", fileOperation="create", device=disk))
        name, marker = self.identity(req)
        config = vim.vm.ConfigSpec(numCPUs=req["cpu"], memoryMB=req["memory_gib"] * 1024, annotation=marker, deviceChange=changes)
        relocate = vim.vm.RelocateSpec(pool=self.pool, datastore=self.store)
        clone = vim.vm.CloneSpec(location=relocate, config=config, powerOn=True, template=False)
        custom = self.service.content.customizationSpecManager.GetCustomizationSpec(name=self.profile["customization_spec"]).spec
        if len(custom.nicSettingMap) != 1 or not isinstance(custom.nicSettingMap[0].adapter.ip, vim.vm.customization.DhcpIpGenerator):
            raise ValueError("初始化规范必须包含单网卡 DHCP 配置")
        identity = custom.identity
        if isinstance(identity, vim.vm.customization.LinuxPrep):
            identity.hostName = vim.vm.customization.FixedName(name=name)
        else:
            raise ValueError("当前交付支持 Linux DHCP 初始化规范")
        clone.customization = custom
        return clone

    def submit(self, req):
        if self.find(req):
            return None
        name, _ = self.identity(req)
        return self.template.CloneVM_Task(folder=self.folder, name=name, spec=self.clone_spec)._moId

    def observe(self, req, task_id):
        from pyVmomi import vmodl

        if task_id:
            try:
                info = self.vim.Task(task_id, self.service._stub).info
            except vmodl.fault.ManagedObjectNotFound:
                info = None
            if info and info.state == "error":
                return {"status": "failed", "reason": type(info.error).__name__}
            if info and info.state != "success":
                return {"status": "pending"}
        machine = self.find(req)
        if not machine or machine.runtime.powerState != "poweredOn":
            return {"status": "pending"}
        guest = machine.guest
        name, _ = self.identity(req)
        address = guest.ipAddress
        if guest.toolsRunningStatus != "guestToolsRunning" or (guest.hostName or "").split(".")[0].lower() != name.lower() or not address:
            return {"status": "pending"}
        ip = ipaddress.ip_address(address)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or not machine.config.instanceUuid:
            return {"status": "pending"}
        return {"status": "success", "vm_id": machine._moId, "vm_uuid": machine.config.instanceUuid, "hostname": name, "ip": str(ip)}


def main():
    from pyVim.connect import Disconnect, SmartConnect

    check = len(sys.argv) == 3 and sys.argv[1] == "--check"
    if len(sys.argv) != 2 and not check:
        raise ValueError("需要交付参数")
    req = decode(sys.argv[-1])
    profile_dir = Path(os.environ.get("BKLITE_VMWARE_PROFILES", "/etc/bklite/vmware/profiles"))
    profile = json.loads((profile_dir / (req["profile"] + ".json")).read_text())
    if normalize_host(profile["host"]) != normalize_host(req["vc_host"]):
        raise ValueError("请求绑定的 CMDB vCenter 与执行机不匹配")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,36}", profile.get("name_prefix", "vm")):
        raise ValueError("交付环境配置无效")
    password_file = Path(profile["password_file"])
    if password_file.stat().st_mode & 0o077:
        raise PermissionError("凭据文件权限过宽")
    connection = SmartConnect(
        host=profile["host"],
        port=profile.get("port", 443),
        user=profile["username"],
        pwd=password_file.read_text().rstrip("\r\n"),
        sslContext=ssl.create_default_context(cafile=profile.get("ca_file")),
        httpConnectionTimeout=30,
    )
    try:
        center = VCenter(connection, profile)
        if check:
            center.validate(req)
            print(json.dumps({"status": "validated", "delivery_id": req["delivery_id"]}))
            return 0
        result = execute(req, center, Path(profile["journal_dir"]), timeout=min(max(int(profile.get("wait_seconds", 1080)), 0), 1080))
        print(json.dumps(result))
        return 0 if result["status"] == "success" else 2
    finally:
        Disconnect(connection)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "unconfirmed", "error_type": type(exc).__name__}))
        sys.exit(1)
