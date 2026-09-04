"""CMDB 企业许可计费模型目录。

只收原生自动发现的基础设施主对象（主机、物理机、云主机、虚拟机、节点、网络设备、独立存储）。
采集入口/平台、K8s 衍生对象、云账号附件、存储内部对象、数据库、中间件默认不计费。
"""

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
