## 说明
该插件通过 pyVmomi 直连 vCenter，采集 vCenter 版本、ESXi 主机硬件与版本、虚拟机名称/IP/规格/所属集群、数据存储名称/类型/容量及宿主关联，输出统一结构供 CMDB 入库

## 前置要求
1. vCenter 已正常运行，可通过 443 端口访问（与接入点网络相通）。
2. 提供只读账号（有权限读取 Datacenter / Cluster / Host / VM / Datastore 清单与配置摘要）。


## 采集内容
**Vcenter(vmware_vc)**

| Key 名称      | 含义 |
| :------------ | :--- |
| vc_version    | vCenter版本号 |
| inst_name     | vCenter名称（关于 vc：显示其名称；其它表里为 名称[MOID]） |

**Esxi(vmware_esxi)**

| Key 名称      | 含义 |
| :------------ | :--- |
| resource_id   | ESXi主机MOID |
| inst_name     | 主机名称[MOID] |
| ip_addr       | 主机管理IP（优先vNIC） |
| memory        | 主机物理内存（MB） |
| cpu_model     | CPU型号 |
| cpu_cores     | 物理核心数 |
| vcpus         | 线程数（逻辑CPU） |
| esxi_version  | ESXi版本 |
| vmware_ds     | 可访问数据存储MOID列表（逗号分隔） |

**VM虚拟机(vmware_vm)**

| Key 名称      | 含义 |
| :------------ | :--- |
| vmware_vm     | 虚拟机对象集合键名 |
| resource_id   | 虚拟机MOID |
| inst_name     | 虚拟机名称[MOID] |
| ip_addr       | 虚拟机首选IP（IPv4优先，其次IPv6） |
| vmware_esxi   | 所在ESXi主机MOID |
| vmware_ds     | 挂载数据存储MOID列表（逗号分隔） |
| cluster       | 所属集群名称（若在集群中） |
| os_name       | 客户操作系统全名 |
| vcpus         | 分配vCPU数量 |
| memory        | 分配内存（MB） |

**存储(vmware_ds)**

| Key 名称      | 含义 |
| :------------ | :--- |
| resource_id   | 数据存储MOID |
| inst_name     | 数据存储名称[MOID] |
| url           | 数据存储URL路径 |
| system_type   | 存储类型（VMFS/NFS等） |
| storage       | 总容量（GB） |
| vmware_esxi   | 关联的ESXi主机MOID列表（逗号分隔） |