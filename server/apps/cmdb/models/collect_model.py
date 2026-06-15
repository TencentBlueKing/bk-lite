# -- coding: utf-8 --
# @File: collect_model.py
# @Time: 2025/2/27 14:04
# @Author: windyzhao

from django.db import models
from django.db.models import JSONField
import copy

from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.core.models.time_info import TimeInfo
from apps.core.models.maintainer_info import MaintainerInfo
from apps.cmdb.constants.constants import (
    CollectPluginTypes,
    CollectDriverTypes,
    CollectRunStatusType,
    CollectInputMethod,
    DataCleanupStrategy,
)
from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.cmdb.constants.constants import SECRET_KEY

# 加密密码的标记前缀
ENCRYPTED_PREFIX = "enc:"
ALLOWED_TOPOLOGY_PROTOCOLS = ("lldp", "cdp", "fdb", "arp")
ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES = (
    "prefer_neighbors_then_fdb_then_arp",
    "strict_neighbors_only",
)
DEFAULT_TOPOLOGY_PROTOCOLS = list(ALLOWED_TOPOLOGY_PROTOCOLS)
DEFAULT_TOPOLOGY_FALLBACK_STRATEGY = "prefer_neighbors_then_fdb_then_arp"
DEFAULT_TOPOLOGY_MIN_CONFIDENCE = 0.0


def normalize_topology_contract(raw_params):
    params = raw_params if isinstance(raw_params, dict) else {}

    topology_protocols = []
    raw_protocols = params.get("topology_protocols")
    if raw_protocols is None:
        topology_protocols = list(DEFAULT_TOPOLOGY_PROTOCOLS)
    elif isinstance(raw_protocols, (list, tuple)):
        for protocol in raw_protocols:
            if protocol in ALLOWED_TOPOLOGY_PROTOCOLS and protocol not in topology_protocols:
                topology_protocols.append(protocol)
        if raw_protocols and not topology_protocols:
            topology_protocols = list(DEFAULT_TOPOLOGY_PROTOCOLS)
    else:
        topology_protocols = list(DEFAULT_TOPOLOGY_PROTOCOLS)

    topology_fallback_strategy = params.get("topology_fallback_strategy")
    if topology_fallback_strategy not in ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES:
        topology_fallback_strategy = DEFAULT_TOPOLOGY_FALLBACK_STRATEGY

    raw_min_confidence = params.get("min_confidence", DEFAULT_TOPOLOGY_MIN_CONFIDENCE)
    try:
        min_confidence = float(raw_min_confidence)
    except (TypeError, ValueError):
        min_confidence = DEFAULT_TOPOLOGY_MIN_CONFIDENCE
    if min_confidence < 0 or min_confidence > 1:
        min_confidence = DEFAULT_TOPOLOGY_MIN_CONFIDENCE

    return {
        "has_network_topo": bool(params.get("has_network_topo")),
        "topology_protocols": topology_protocols,
        "topology_fallback_strategy": topology_fallback_strategy,
        "min_confidence": min_confidence,
    }


class CollectModels(MaintainerInfo, TimeInfo):
    """
    专业采集-协议-云-vm-snmp-k8s
    """

    name = models.CharField(max_length=128, help_text="任务名称")
    task_type = models.CharField(max_length=32, choices=CollectPluginTypes.CHOICE, help_text="任务类型")
    driver_type = models.CharField(max_length=32, choices=CollectDriverTypes.CHOICE,
                                   default=CollectDriverTypes.PROTOCOL, help_text="驱动类型")
    model_id = models.CharField(max_length=64, help_text="模型ID")

    is_interval = models.BooleanField(default=False, help_text="是否开启周期巡检")
    cycle_value_type = models.CharField(max_length=32, help_text="周期任务类型")
    cycle_value = models.CharField(max_length=32, blank=True, null=True, help_text="周期任务值")
    scan_cycle = models.CharField(max_length=50, blank=True, null=True, help_text="扫描周期")

    ip_range = models.TextField(blank=True, null=True, help_text="IP范围")
    instances = JSONField(default=list, help_text="实例")

    access_point = JSONField(default=dict, help_text="接入点")
    credential = JSONField(default=list, help_text="凭据")

    timeout = models.PositiveSmallIntegerField(default=0, help_text="超时时间(单个ip)")

    exec_status = models.PositiveSmallIntegerField(default=CollectRunStatusType.NOT_START,
                                                   choices=CollectRunStatusType.CHOICE, help_text="执行状态")
    exec_time = models.DateTimeField(blank=True, null=True, help_text="执行时间")

    task_id = models.CharField(max_length=64, blank=True, null=True, help_text="任务执行id")

    params = JSONField(default=dict, help_text="采集任务额外的参数(各种实例或者不包括在凭据里的参数)")

    plugin_id = models.IntegerField(default=0, help_text="采集插件ID")

    input_method = models.PositiveSmallIntegerField(default=CollectInputMethod.AUTO, choices=CollectInputMethod.CHOICE,
                                                    help_text="录入方式")

    data_cleanup_strategy = models.CharField(
        max_length=32, choices=DataCleanupStrategy.CHOICE, default=DataCleanupStrategy.DEFAULT, help_text="数据清理策略"
    )
    expire_days = models.PositiveSmallIntegerField(default=0, help_text="过期天数")

    collect_data = JSONField(default=dict, help_text="采集原数据")
    collect_digest = JSONField(default=dict, help_text="采集摘要数据")
    format_data = JSONField(default=dict, help_text="采集返回的分类后的数据")
    topology_snapshot = models.JSONField(default=dict, blank=True, verbose_name="拓扑链路快照与过程数据")
    team = JSONField(default=list, help_text="关联组织")  # 把params里的组织单独抽出来，方便权限控制

    is_system = models.BooleanField(default=False, help_text="是否为系统内置任务")
    is_visible = models.BooleanField(default=True, help_text="是否在普通采集页面展示")
    system_code = models.CharField(max_length=128, blank=True, null=True, help_text="系统任务编码")

    class Meta:
        verbose_name = "采集任务"
        unique_together = ("name", "driver_type", "model_id")

    @property
    def info(self):
        # 详情
        add_data = self.format_data.get("add", [])
        update_data = self.format_data.get("update", [])
        delete_data = self.format_data.get("delete", [])
        relation_data = self.format_data.get("association", [])
        raw_data = self.format_data.get("__raw_data__", [])

        # 拓扑摘要数据源：新流水线把解析后的链路存进 topology_snapshot，
        # 前端「拓扑摘要」面板据此渲染（旧的 network_topology_facts_info_gauge 指标已废弃，
        # 不再出现在 raw_data 中，前端不能再以它为数据源）。
        snapshot = self.topology_snapshot or {}

        return {
            "add": {"data": add_data, "count": len(add_data)},
            "update": {"data": update_data, "count": len(update_data)},
            "delete": {"data": delete_data, "count": len(delete_data)},
            "relation": {"data": relation_data, "count": len(relation_data)},
            "raw_data": {"data": raw_data, "count": len(raw_data)},
            "topology": {
                "summary": snapshot.get("summary", {}),
                "links": snapshot.get("links", []),
                "stale_links": snapshot.get("stale_links", []),
                "unresolved_neighbors": snapshot.get("unresolved_neighbors", []),
                "dropped": snapshot.get("dropped", []),
            },
        }

    @property
    def is_k8s(self):
        return self.task_type == CollectPluginTypes.K8S

    @property
    def is_network_topo(self):
        return self.topology_contract["has_network_topo"]

    @property
    def topology_contract(self):
        return normalize_topology_contract(self.params)

    @property
    def topology_protocols(self):
        return self.topology_contract["topology_protocols"]

    @property
    def topology_fallback_strategy(self):
        return self.topology_contract["topology_fallback_strategy"]

    @property
    def min_confidence(self):
        return self.topology_contract["min_confidence"]

    @property
    def is_cloud(self):
        return self.task_type == CollectPluginTypes.CLOUD

    @property
    def is_job(self):
        return self.driver_type == CollectDriverTypes.JOB

    @property
    def is_host(self):
        return self.task_type == CollectPluginTypes.HOST

    @property
    def is_db(self):
        return self.task_type == CollectPluginTypes.DB

    @staticmethod
    def encrypt_password(raw_password):
        """
        加密密码
        :param raw_password: 明文密码
        :return: 加密后的密码（带enc:前缀）
        """
        if not raw_password:
            return raw_password

        # 如果已经加密过，直接返回
        if isinstance(raw_password, str) and raw_password.startswith(ENCRYPTED_PREFIX):
            return raw_password

        crypto = PasswordCrypto(SECRET_KEY)
        encrypted = crypto.encrypt(raw_password)
        return f"{ENCRYPTED_PREFIX}{encrypted}"

    @staticmethod
    def decrypt_password(password):
        """
        解密密码
        :return: 明文密码
        """
        if not password:
            return password

        # 去除加密前缀
        encrypted_text = password
        if isinstance(password, str) and password.startswith(ENCRYPTED_PREFIX):
            encrypted_text = password[len(ENCRYPTED_PREFIX):]

        try:
            crypto = PasswordCrypto(SECRET_KEY)
            return crypto.decrypt(encrypted_text)
        except Exception:  # noqa: BLE001 - 解密失败时回退到明文密码
            # 如果解密失败，可能是明文密码，直接返回
            return password

    @property
    def decrypt_credentials(self):
        """
        解密凭据中的密码字段
        :return: 解密后的凭据列表
        {"port": "22", "password": "password", "username": "admin"}
        """
        if not self.credential:
            return self.credential

        encrypted_fields = get_collect_model_passwords(collect_model_id=self.model_id, driver_type=self.driver_type)

        def decrypt_item(raw_item):
            item = copy.deepcopy(raw_item)
            if not isinstance(item, dict):
                return item
            for encrypted_field in encrypted_fields:
                password = item.get(encrypted_field)
                if not password:
                    continue
                item[encrypted_field] = self.decrypt_password(password)
            return item

        if isinstance(self.credential, list):
            return [decrypt_item(item) for item in self.credential]
        if isinstance(self.credential, dict):
            return decrypt_item(self.credential)
        return self.credential

    def save(self, *args, **kwargs):
        # 只有在密码未加密时才进行加密
        if self.credential:
            encrypted_fields = get_collect_model_passwords(collect_model_id=self.model_id, driver_type=self.driver_type)

            def encrypt_item(raw_item):
                if not isinstance(raw_item, dict):
                    return raw_item
                item = copy.deepcopy(raw_item)
                for encrypted_field in encrypted_fields:
                    password = item.get(encrypted_field)
                    if not password:
                        continue
                    if isinstance(password, str) and password.startswith(ENCRYPTED_PREFIX):
                        continue
                    item[encrypted_field] = self.encrypt_password(password)
                return item

            if isinstance(self.credential, list):
                self.credential = [encrypt_item(item) for item in self.credential]
            elif isinstance(self.credential, dict):
                self.credential = encrypt_item(self.credential)
        super().save(*args, **kwargs)


class OidMapping(MaintainerInfo, TimeInfo):
    """
    oid库映射表
    """

    model = models.CharField(max_length=128, null=True, verbose_name="设备型号")
    oid = models.CharField(max_length=64, unique=True, help_text="设备oid")
    brand = models.CharField(max_length=64, null=True, help_text="品牌")
    device_type = models.CharField(max_length=128, help_text="设备类型")
    built_in = models.BooleanField(default=False, verbose_name="是否内置")
