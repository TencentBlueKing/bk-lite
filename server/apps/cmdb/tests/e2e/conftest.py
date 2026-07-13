"""端到端流水线测试公共 fixture。

复用上层 apps/cmdb/tests/conftest.py 的 fake_graph fixture（pytest 自动继承）。
"""
import json
from pathlib import Path
from typing import Any, Optional, Tuple

import pytest

E2E_ROOT = Path(__file__).parent


# --------------------------------------------------------------------------
# fixture 装载工具
# --------------------------------------------------------------------------


def _load(rel_path: str) -> Any:
    """从 fixtures/ 或 schemas/ 读 JSON。"""
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def load_fixture():
    """test 里写 load_fixture('host/01_shell_output.json')。"""

    def _impl(rel_path: str):
        return _load(f"fixtures/{rel_path}")

    return _impl


@pytest.fixture
def load_schema():
    """test 里写 load_schema('host/01_shell_output.schema.json')。"""

    def _impl(rel_path: str):
        return _load(f"schemas/{rel_path}")

    return _impl


# --------------------------------------------------------------------------
# v4 Phase 1.2:load_runner_plugin_for_model_id 工厂
# --------------------------------------------------------------------------
# 根据 model_id 返回 (runner_cls, plugin_cls, extra_payload_keys) 三元组
# 覆盖 v3+ 全部 27 个真实落盘对象
# 三个 runner 形态:
#   - protocol:ProtocolCollectMetrics + extra_payload_keys=None
#   - db:DBCollectCollectMetrics + extra_payload_keys=None
#   - middleware:MiddlewareCollectMetrics + extra_payload_keys={"result": True}


def _resolve_plugin(model_id: str):
    """根据 model_id 在 apps/cmdb/collection/plugins/community/ 下找 plugin 类。

    优先在子目录中按 model_id 找 *.py 文件,失败则尝试 mysql→protocol,mysql→db 等兼容路径。
    返回 plugin 类(继承 BaseXxxCollectionPlugin 的具体子类,不是基类本身)。

    支持 model_id → 插件模块名 别名(stargazer 端 model_id 与 plugin supported_model_id 不一致时使用)。
    例如 stargazer 落盘 model_id='elasticsearch',而 ESCollectionPlugin.supported_model_id='es'
    且插件模块名是 db/es.py,需要在 db.es 目录里查找。
    """
    # model_id → 插件模块短名 别名表(用于 stargazer model_id 与 plugin 文件名不一致场景)
    # 例 1:stargazer 落盘 model_id='elasticsearch',plugin 类 supported_model_id='es' 且模块名是 db/es.py
    # 例 2:stargazer 落盘 model_id='hwcloud_ecs'(子对象),plugin 类定义在 cloud/hwcloud.py(父 plugin)
    _PLUGIN_MODULE_ALIAS = {
        "elasticsearch": "es",
        # Task 3.1:hwcloud 子对象共用 cloud/hwcloud.py 父 plugin
        "hwcloud_ecs": "hwcloud",
        "hwcloud_vpc": "hwcloud",
        "hwcloud_evs": "hwcloud",
        "hwcloud_obs": "hwcloud",
        "hwcloud_subnet": "hwcloud",
        "hwcloud_eip": "hwcloud",
        "hwcloud_sg": "hwcloud",
        "hwcloud_elb": "hwcloud",
        "hwcloud_rds": "hwcloud",
        "hwcloud_dcs": "hwcloud",
        # Task 3.2:qcloud 子对象共用 cloud/qcloud.py 父 plugin
        "qcloud_bucket": "qcloud",
        "qcloud_clb": "qcloud",
        "qcloud_cmq": "qcloud",
        "qcloud_cmq_topic": "qcloud",
        "qcloud_cvm": "qcloud",
        "qcloud_domain": "qcloud",
        "qcloud_eip": "qcloud",
        "qcloud_filesystem": "qcloud",
        "qcloud_mongodb": "qcloud",
        "qcloud_mysql": "qcloud",
        "qcloud_pgsql": "qcloud",
        "qcloud_plusar_cluster": "qcloud",
        "qcloud_pulsar_cluster": "qcloud",
        "qcloud_redis": "qcloud",
        "qcloud_rocketmq": "qcloud",
        # Task 3.3:fusioninsight 子对象共用 cloud/fusioninsight.py 父 plugin
        "fusioninsight_cluster": "fusioninsight",
        "fusioninsight_host": "fusioninsight",
        # Task 3.4 / 3.5:zstack / h3c_cas 无 plugin(stub)
        # 已在 _PLUGIN_MODULE_ALIAS 处理:stub module 名 = model_id
        # Task 3.6 / 3.7:dameng_enterprise / redis_sentinel_enterprise 复用底层 plugin
        # 注:redis_sentinel 的实际 plugin 模块是 db/redis.py(因为 bk_obj_id='redis')
        # 所以 redis_sentinel_enterprise 也要 alias 到 redis 才能找到 plugin
        "dameng_enterprise":          "dameng",  # 复用社区版 dameng plugin
        "redis_sentinel_enterprise":  "redis",  # 复用 redis plugin(db/redis.py)
    }
    module_alias = _PLUGIN_MODULE_ALIAS.get(model_id, model_id)

    # 三种可能路径(按命中优先)
    candidate_modules = [
        f"apps.cmdb.collection.plugins.community.db.{module_alias}",
        f"apps.cmdb.collection.plugins.community.db.{model_id}",
        f"apps.cmdb.collection.plugins.community.middleware.{module_alias}",
        f"apps.cmdb.collection.plugins.community.middleware.{model_id}",
        f"apps.cmdb.collection.plugins.community.protocol.{module_alias}",
        f"apps.cmdb.collection.plugins.community.protocol.{model_id}",
        # Task 3:云采集 plugin(plugins/community/cloud/)— 子对象走父 plugin
        # 例:hwcloud_ecs → 父 plugin module = hwcloud(因 plugin 类只在 hwcloud.py 定义)
        f"apps.cmdb.collection.plugins.community.cloud.{module_alias}",
        f"apps.cmdb.collection.plugins.community.cloud.{model_id}",
        # Task 4:archived 对象 plugin(plugins/community/archived/)— license/集群/平台占位
        # 例:apusic → plugin module = apusic(因 plugin 类只在 archived/apusic.py 定义)
        f"apps.cmdb.collection.plugins.community.archived.{module_alias}",
        f"apps.cmdb.collection.plugins.community.archived.{model_id}",
    ]
    last_err: Optional[Exception] = None
    for mod_path in candidate_modules:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
        except ModuleNotFoundError as e:
            last_err = e
            continue
        # 在 module 里找以 model_id 开头且以 CollectionPlugin 结尾的具体子类
        # 过滤掉 BaseXxxCollectionPlugin 这种基类
        target_prefix = model_id.replace("_", "").lower()
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if not isinstance(cls, type):
                continue
            if not attr_name.endswith("CollectionPlugin"):
                continue
            # 跳过基类(BaseProtocolCollectionPlugin / BaseDBCollectionPlugin / BaseMiddlewareCollectionPlugin)
            if attr_name.startswith("Base"):
                continue
            # 优先匹配以 model_id 开头的(如 InfluxdbCollectionPlugin)
            if attr_name.lower().replace("_", "").startswith(target_prefix):
                return cls
        # 如果该 module 找到了但没有前缀匹配,fallback:取第一个非 Base 的 CollectionPlugin
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if not isinstance(cls, type):
                continue
            if not attr_name.endswith("CollectionPlugin"):
                continue
            if attr_name.startswith("Base"):
                continue
            return cls
    raise KeyError(
        f"model_id={model_id!r}: 未在 db/middleware/protocol 三个子目录找到 plugin 类。"
        f"候选模块: {candidate_modules};最后错误: {last_err}。"
        f"说明:此 model_id 在 stargazer 端有 catalog,但 CMDB 端尚未实现 plugin 类。"
        f"属于 v4 排除对象,不在 e2e 覆盖范围。"
    )


# model_id → (大类, extra_payload_keys) 映射表
# 大类决定用哪个 runner
_MODEL_RUNNER_MAP = {
    # protocol 大类(业务字段平铺,无 metric.result 解析)
    "influxdb":     ("protocol",   None),
    "mssql":        ("protocol",   None),
    "oracle":       ("protocol",   None),
    "elasticsearch": ("db",         None),  # alias:es(同 db 平铺)
    "es":           ("db",         None),
    "redis_sentinel": ("middleware", {"result": True}),  # 走 middleware(redis + sentinel 双端口)
    # db 大类(平铺,runner 用 DatabasesCollectMetrics,实际类是 DBCollectCollectMetrics)
    "mysql":        ("db",         None),
    "postgresql":   ("db",         None),
    "redis":        ("db",         None),
    "mongodb":      ("db",         None),
    "es":           ("db",         None),
    "hbase":        ("db",         None),
    "dameng":       ("db",         None),
    "tongweb":      ("db",         None),
    # middleware 大类(业务字段经 metric.result JSON 编码)
    "nginx":        ("middleware", {"result": True}),
    "openresty":    ("middleware", {"result": True}),
    "apache":       ("middleware", {"result": True}),
    "tomcat":       ("middleware", {"result": True}),
    "jboss":        ("middleware", {"result": True}),
    "jetty":        ("middleware", {"result": True}),
    "iis":          ("middleware", {"result": True}),
    "rabbitmq":     ("middleware", {"result": True}),
    "kafka":        ("middleware", {"result": True}),
    "rocketmq":     ("middleware", {"result": True}),
    "activemq":     ("middleware", {"result": True}),
    "zookeeper":    ("middleware", {"result": True}),
    "etcd":         ("middleware", {"result": True}),
    "consul":       ("middleware", {"result": True}),
    "haproxy":      ("middleware", {"result": True}),
    "keepalived":   ("middleware", {"result": True}),
    "memcached":    ("middleware", {"result": True}),
    "minio":        ("middleware", {"result": True}),
    "squid":        ("middleware", {"result": True}),
    "docker":       ("middleware", {"result": True}),
    # Task 3:云采集 plugin 走各自云厂商 collector(HwCloud / QCloud / FusionInsight)
    # model_field_mapping 由 plugin.field_mappings 字典提供(每个 sub-model 各自 bind)
    "hwcloud_ecs":     ("cloud_hwcloud",   None),
    "hwcloud_vpc":     ("cloud_hwcloud",   None),
    "qcloud_cvm":      ("cloud_qcloud",    None),
    "qcloud_clb":      ("cloud_qcloud",    None),
    "qcloud_redis":    ("cloud_qcloud",    None),
    "qcloud_bucket":   ("cloud_qcloud",    None),
    "qcloud_cmq":      ("cloud_qcloud",    None),
    "qcloud_mysql":    ("cloud_qcloud",    None),
    "qcloud_mongodb":  ("cloud_qcloud",    None),
    "fusioninsight_cluster": ("cloud_fusioninsight", None),
    "fusioninsight_host":    ("cloud_fusioninsight", None),
    # zstack / h3c_cas:stub plugin,云厂商特定 collector 也不存在,先用 cloud_generic stub
    "zstack":  ("cloud_stub", None),
    "h3c_cas": ("cloud_stub", None),
    # dameng_enterprise / redis_sentinel_enterprise 复用底层 plugin
    "dameng_enterprise":         ("db",         None),  # 复用 db runner + dameng plugin
    "redis_sentinel_enterprise": ("middleware", {"result": True}),  # 复用 redis_sentinel
    # Task 4:22 个 archived placeholder 对象(17 license + 3 cluster + 1 host 平台 + 1 host 集群)
    # license 类:全部 MIDDLEWARE task_type,走 middleware runner
    "apusic":        ("middleware", {"result": True}),
    "bes":           ("middleware", {"result": True}),
    "informix":      ("middleware", {"result": True}),
    "ihs":           ("middleware", {"result": True}),
    "inforsuite_as": ("middleware", {"result": True}),
    "iris":          ("middleware", {"result": True}),
    "couchbase":     ("middleware", {"result": True}),
    "oceanbase":     ("middleware", {"result": True}),
    "oscar":         ("middleware", {"result": True}),
    "sap_hana":      ("middleware", {"result": True}),
    "sybase":        ("middleware", {"result": True}),
    "tonggtp":       ("middleware", {"result": True}),
    "tonglinkq":     ("middleware", {"result": True}),
    "tongrds":       ("middleware", {"result": True}),
    "tuxedo":        ("middleware", {"result": True}),
    "weblogic":      ("middleware", {"result": True}),
    "websphere":     ("middleware", {"result": True}),
    # cluster 类:PROTOCOL task_type(hdfs/storm/yarn),HOST task_type(mycat)
    # 全部用 protocol runner(archived plugin 无 metric_names,protocol runner 在 step2 push_to_vm
    # 仍能产出主 metric;B 端对齐由 _placeholder_reason 跳过 pipeline 验证)
    "hdfs":          ("protocol",   None),
    "storm":         ("protocol",   None),
    "yarn":          ("protocol",   None),
    "mycat":         ("protocol",   None),
    # platform 类:HOST task_type(domestic_linux 国产 Linux 平台约束)
    "domestic_linux": ("protocol",  None),
}


def load_runner_plugin_for_model_id(model_id: str) -> Tuple[type, type, Optional[dict]]:
    """根据 model_id 返回 (runner_cls, plugin_cls, extra_payload_keys) 三元组。

    覆盖 v3+ 全部 27 个真实落盘对象(main 7 + worktree 20)。
    失败时抛 KeyError 并给出明确错误信息(便于 review 时定位)。

    用法:
        runner_cls, plugin_cls, extra = load_runner_plugin_for_model_id("influxdb")
        # → (ProtocolCollectMetrics, InfluxdbCollectionPlugin, None)
    """
    if model_id not in _MODEL_RUNNER_MAP:
        raise KeyError(
            f"model_id={model_id!r} 不在 _MODEL_RUNNER_MAP 覆盖范围。"
            f"已覆盖({len(_MODEL_RUNNER_MAP)} 个): {sorted(_MODEL_RUNNER_MAP.keys())}。"
            f"如需新增,请在 conftest.py 末尾的映射表中追加 model_id → (大类, extra_payload_keys) 一行。"
        )
    runner_type, extra_payload_keys = _MODEL_RUNNER_MAP[model_id]
    if runner_type == "protocol":
        from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
        runner_cls = ProtocolCollectMetrics
    elif runner_type == "db":
        from apps.cmdb.collection.collect_plugin.databases import DBCollectCollectMetrics
        runner_cls = DBCollectCollectMetrics
    elif runner_type == "middleware":
        from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
        runner_cls = MiddlewareCollectMetrics
    elif runner_type == "cloud_hwcloud":
        from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
        runner_cls = HwCloudCollectMetrics
    elif runner_type == "cloud_qcloud":
        from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics
        runner_cls = QCloudCollectMetrics
    elif runner_type == "cloud_fusioninsight":
        from apps.cmdb.collection.collect_plugin.fusioninsight import FusionInsightCollectMetrics
        runner_cls = FusionInsightCollectMetrics
    elif runner_type == "cloud_stub":
        # zstack / h3c_cas:无云厂商特定 collector,用 ProtocolCollectMetrics 作 stub 载体
        from apps.cmdb.collection.collect_plugin.protocol import ProtocolCollectMetrics
        runner_cls = ProtocolCollectMetrics
    else:
        raise KeyError(f"未知的 runner_type={runner_type!r}(model_id={model_id!r})")
    plugin_cls = _resolve_plugin(model_id)
    return runner_cls, plugin_cls, extra_payload_keys


@pytest.fixture
def runner_plugin_factory():
    """test 里用 runner_plugin_factory('influxdb') 拿三元组。"""
    return load_runner_plugin_for_model_id


# --------------------------------------------------------------------------
# in-memory NATS 替身（配置文件采集那条路用；host 类不走 NATS 订阅）
# --------------------------------------------------------------------------


class FakeNatsClient:
    """
    模拟 server 端的 nats_client：
    - publish(subject, data) → 同步派发到本进程内已 register 的 handler
    - register(fn) → 收集 handler

    用法：
        from apps.cmdb.nats import nats as cmdb_nats
        fake = FakeNatsClient()
        fake.register_handlers_from_module(cmdb_nats)
        result = fake.publish("receive_config_file_result", payload)
    """

    def __init__(self):
        self.handlers: dict = {}
        self.published: list = []

    def register_handlers_from_module(self, module):
        for name in dir(module):
            fn = getattr(module, name)
            if callable(fn) and getattr(fn, "_nats_registered", False):
                self.handlers[name] = fn

    def publish(self, subject: str, data: Any):
        self.published.append((subject, data))
        fn = self.handlers.get(subject)
        if fn is None:
            return None
        return fn(data)


@pytest.fixture
def fake_nats():
    return FakeNatsClient()


# ============================================================================
# A/B 端对齐检查 fixture(Task 1.6)
# ============================================================================
# 35 个新工作对象(P0/P1/P2 覆盖),不动现有 33 真实落盘对象
# P1/P2 逐对象在 Task 3/4 加进来

ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6)
    "aliyun_ecs",
    "k8s_namespace",
    "vmware",
    "host",
    "network",
    "config_file",
    # P1 云采集新增(7) — Task 3
    "hwcloud_ecs",     # Task 3.1
    "hwcloud_vpc",     # Task 3.1
    "qcloud_cvm",      # Task 3.2
    "qcloud_clb",      # Task 3.2
    "qcloud_redis",    # Task 3.2
    "qcloud_bucket",   # Task 3.2
    "qcloud_cmq",      # Task 3.2
    "qcloud_mysql",    # Task 3.2
    "qcloud_mongodb",  # Task 3.2
    "fusioninsight_cluster",  # Task 3.3
    "fusioninsight_host",     # Task 3.3
    "zstack",          # Task 3.4
    "h3c_cas",         # Task 3.5
    "dameng_enterprise",         # Task 3.6
    "redis_sentinel_enterprise", # Task 3.7
    # P2 archived placeholder(22) — Task 4
    # 17 license 类(MIDDLEWARE task_type)
    "apusic",        # Task 4.1
    "bes",           # Task 4.2
    "informix",      # Task 4.3
    "ihs",           # Task 4.4
    "inforsuite_as", # Task 4.5
    "iris",          # Task 4.6
    "couchbase",     # Task 4.7
    "oceanbase",     # Task 4.8
    "oscar",         # Task 4.9
    "sap_hana",      # Task 4.10
    "sybase",        # Task 4.11
    "tonggtp",       # Task 4.12
    "tonglinkq",     # Task 4.13
    "tongrds",       # Task 4.14
    "tuxedo",        # Task 4.15
    "weblogic",      # Task 4.16
    "websphere",     # Task 4.17
    # 5 集群/平台类
    "hdfs",          # Task 4.18
    "storm",         # Task 4.19
    "yarn",          # Task 4.20
    "mycat",         # Task 4.21
    "domestic_linux", # Task 4.22
]


@pytest.fixture
def alignment_covered_model_ids():
    """A/B 端对齐检查覆盖的 model_id 列表。"""
    return ALIGNMENT_COVERED_MODEL_IDS
