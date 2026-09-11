"""CMDB 企业许可计费模型目录。

只收原生自动发现的基础设施主对象（主机、物理机、云主机、虚拟机、节点、网络设备、独立存储）。
采集入口/平台、K8s 衍生对象、云账号附件、存储内部对象、数据库、中间件默认不计费。

许可用量计数时，操作系统（host）与虚拟机按 ip_addr 去重：虚拟机 IP 命中任一 host IP 则该虚拟机不计，host 保留。
第一版不按云区域拆 IP，不同 cloud 撞同一私网 IP 可能误并。空 IP 的虚拟机不去重，继续计数。
"""

CMDB_LICENSE_OS_MODEL_ID = "host"

CMDB_LICENSE_VM_MODEL_IDS = frozenset(
    {
        "vmware_vm",
        "aliyun_ecs",
        "qcloud_cvm",
        "hwcloud_ecs",
        "aws_ec2",
        "azure_vm",
        "fusioncompute_vm",
        "h3c_cas_vm",
        "nutanixhci_vm",
        "openstack_vm",
        "sangforscp_vm",
        "sangforhci_vm",
        "smartx_vm",
        "winsphere_vm",
        "inspurincloudrail_vm",
    }
)

CMDB_LICENSE_MODEL_IDS = frozenset(
    {
        "host",
        "physcial_server",
        "k8s_node",
        "vmware_esxi",
        "vmware_vm",
        "aliyun_ecs",
        "qcloud_cvm",
        "hwcloud_ecs",
        "aws_ec2",
        "azure_vm",
        "fusioninsight_host",
        "fusioncompute_host",
        "fusioncompute_vm",
        "h3c_cas_host",
        "h3c_cas_vm",
        "nutanixhci_host",
        "nutanixhci_vm",
        "openstack_node",
        "openstack_vm",
        "sangforscp_host",
        "sangforscp_vm",
        "sangforhci_vm",
        "smartx_host",
        "smartx_vm",
        "winsphere_host",
        "winsphere_vm",
        "manageone_host",
        "manageone_server",
        "inspurincloudrail_vm",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "security_device",
        "storage",
    }
)
