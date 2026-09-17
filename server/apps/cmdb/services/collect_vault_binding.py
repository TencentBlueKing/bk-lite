"""采集入口到系统管理内置凭据类型的绑定。"""

from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.system_mgmt.models import CredentialType
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

# 按插件实际认证通道和对象分类绑定；对象是数据库并不代表使用数据库账户。
# PC Windows 使用 WinRM，macOS 使用 SSH；协议入口继续按实际认证契约绑定。
COLLECT_VAULT_BINDINGS = {
    "host/ssh": "docker host config_file physcial_server hmc".split(),
    "cloud/platform_api": (
        "vmware_vc zstack h3c_cas winsphere smartx manageone fusioncompute sangforhci sangforscp nutanixhci " "inspurincloudrail fusioninsight"
    ).split(),
    "cloud/openstack": "openstack".split(),
    "network/snmp": "network f5 security_device".split(),
    "network/ssh": "brocade_fc cisco_fc network_config_file".split(),
    "database/sql": (
        "mysql postgresql mssql oceanbase highgo couchbase sap_hana iris tongrds tdsql gbase8a greenplum kingbase " "opengauss vastbase"
    ).split(),
    "database/token": "influxdb".split(),
    "database/ssh": "redis mongodb es hbase informix sybase mycat redis_sentinel gbase8s oscar dameng db2 tidb".split(),
    "storage/platform_api": (
        "storage dell_unity netapp_ontap ibm_storwize emc_symmetrix hds_vsp pure_array netapp_cluster oraclezfs " "infinidat dell_powerstore hp_3par"
    ).split(),
    "storage/cloud": "ibm_ds xsky".split(),
    "storage/snmp": "macrosan tape_library".split(),
    "cloud/cloud": "aliyun_account qcloud hwcloud aws".split(),
    "cloud/oauth_client": "azure".split(),
    "host/ipmi": "physcial_server_ipmi".split(),
    "host/redfish": "physcial_server_redfish server_bmc".split(),
    "host/winrm": "pc".split(),
    "middleware/ssh": (
        "nginx minio zookeeper kafka consul etcd rabbitmq tomcat apache activemq iis tuxedo memcached rocketmq openresty "
        "squid haproxy keepalive spark ibmmq tonglinkq tonggtp ihs cics hdfs yarn storm bes apusic inforsuite_as ceph "
        "jboss jetty tongweb weblogic websphere"
    ).split(),
    "middleware/sql": "nacos ambari".split(),
}

_BY_OBJECT = {object_id: binding for binding, ids in COLLECT_VAULT_BINDINGS.items() for object_id in ids}
_BY_OBJECT.update(
    {
        "oracle": "database/sql",
        "pgsql": "database/sql",
        "network_topo": "network/snmp",
        "aliyun": "cloud/cloud",
        "keepalived": "middleware/ssh",
    }
)


def binding_for_collect_object(object_id, *, model_id=None, driver_type=None, protocol=None, os_type=None):
    """同一 model 的 SSH/IPMI/Redfish 与 PC OS 分支按实际入口区分。"""
    # 旧任务 driver 标签可能为 job，但这两个模型的现有 NodeParams 仍按数据库直连构建参数。
    if model_id in {"mysql", "postgresql", "pgsql"} and driver_type == "job":
        return "database/sql"
    if model_id == "physcial_server":
        if driver_type == "protocol":
            return "host/redfish" if protocol == "redfish" else "host/ipmi"
        return "host/ssh"
    if model_id == "pc":
        return "host/ssh" if str(os_type or "").lower() in {"macos", "mac", "darwin"} else "host/winrm"
    return _BY_OBJECT.get(object_id) or _BY_OBJECT.get(model_id)


def actual_builtin_type_keys(binding, type_rows=None):
    """返回目录中真实可用的内置 key，避免首选 key 被自定义类型占用。"""
    if not binding:
        return []
    category, preferred_key = binding.split("/", 1)
    candidate_keys = [preferred_key]
    if preferred_key == "openstack":
        candidate_keys.append("openstack_account")
    elif preferred_key == "redfish":
        candidate_keys.append("redfish_bmc")
    rows = type_rows if type_rows is not None else CredentialType.objects.filter(key__in=candidate_keys, is_builtin=True)
    expected_auth = {
        field["id"]: field.get("kind")
        for field in BUILTIN_TYPES[preferred_key]["fields"]
        if field["id"] in (CollectCredentialPoolService.VAULT_CORE_FIELDS | {"version"})
    }
    usable = []
    for row in rows:
        if not row.is_builtin or row.key not in candidate_keys or category not in (row.categories or []):
            continue
        if hasattr(row, "fields"):
            actual_auth = {field.get("id"): field.get("kind") for field in (row.fields or [])}
            if any(actual_auth.get(field_id) != kind for field_id, kind in expected_auth.items()):
                continue
        usable.append(row.key)
    return usable
