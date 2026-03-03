### 说明
该插件通过 pyVmomi 直连 vCenter，采集 vCenter 版本、ESXi 主机硬件与版本、虚拟机名称/IP/规格/所属集群、数据存储名称/类型/容量及宿主关联，输出统一结构供 CMDB 入库。

本文档同时包含两部分：
1. 面向非专业 VMware 运维的操作步骤（如何准备与配置）。
2. 字段字典（采集到 CMDB 的字段含义）。



### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **vCenter**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。



### 前置要求
1. 网络连通：接入点到 vCenter 的 `443/TCP` 连通。
2. 账号准备：建议创建专用采集账号，并授予只读权限（Read-only），且对上层对象授予并继承（propagate）。
3. 资产准备：如果页面“vCenter 下拉选择”为空，请先在 CMDB 资产数据中维护 vCenter 资产（包含管理地址）。




### 操作步骤
### 步骤 1：网络连通性自测（接入点执行）
- Linux：
	- `nc -vz <vcenter_host> 443`
	- `curl -k https://<vcenter_host>:443/ -I`
- Windows PowerShell：
	- `Test-NetConnection <vcenter_host> -Port 443`

判断标准：端口连通即可。若 `curl` 报证书错误，属于常见现象，可先在页面关闭 SSL 验证用于验证流程（见下文）。


### 步骤 2：在 CMDB 上创建采集任务（页面操作）
在新增任务时，你只需要重点关注“凭据/鉴权”相关字段：

- `username`：vCenter 登录用户名（建议使用只读账号）。
- `password`：上述用户的登录密码。
- `port`：vCenter API 端口（通常为 `443`）。
- `sslVerify`：是否校验 vCenter HTTPS 证书。若 vCenter 使用自签证书且接入点未安装信任链，可先关闭用于验证流程，后续再补齐证书信任并开启。



### 采集内容（字段字典）
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
| annotation    | vCenter 备注（vm.summary.config.annotation） |
| uptime_seconds | 本次开机累计秒数（vm.summary.quickStats.uptimeSeconds；关机/不可用为 0） |
| tools_version | VMware Tools 版本号（vm.guest.toolsVersion） |
| tools_status  | VMware Tools 安装状态（vm.guest.toolsStatus） |
| tools_running_status | VMware Tools 运行状态（vm.guest.toolsRunningStatus） |
| last_boot     | 本次开机时间（vm.runtime.bootTime；关机为 None） |
| creation_date | 创建时间（vm.config.createDate；vSphere 6.7+） |
| last_backup   | 上次备份时间（自定义字段，如 NB_LAST_BACKUP） |
| backup_policy | 备份策略（自定义字段，如 NB_BACKUP_POLICY） |
| data_disks    | 磁盘明细 JSON（单盘维度：disk_id/provisioned_gb/used_gb/disk_type/datastore；layoutEx 不可用时 used_gb 为 null） |

**存储(vmware_ds)**

| Key 名称      | 含义 |
| :------------ | :--- |
| resource_id   | 数据存储MOID |
| inst_name     | 数据存储名称[MOID] |
| url           | 数据存储URL路径 |
| system_type   | 存储类型（VMFS/NFS等） |
| storage       | 总容量（GB） |
| vmware_esxi   | 关联的ESXi主机MOID列表（逗号分隔） |
