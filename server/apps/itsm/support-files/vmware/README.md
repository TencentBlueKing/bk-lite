# VMware 交付执行机

作业脚本为 `provision_vm.py`，使用 Python 3 和 `pyvmomi==9.0.0.0`。ITSM 在审批通过后读取仓库内置脚本并以 Python 作业下发；顺序传递一个位置参数 `payload`，任务超时为 1200 秒。一次调用交付一台 Linux 虚拟机。

## 批量申请

申请人在「虚拟机明细」中每行配置一台，选择规格、系统模板、网络、数据盘策略和容量。台数取实际行数，单次上限取服务目录的 `max_quantity`。容量使用 GiB 整数，0 表示无需数据盘。运维审批整张工单，交付时系统按批准的行顺序生成独立交付编号和作业。

工单保存原始选项 ID 和容量，Flowable 的 `form_vm_requests` 是有序 JSON 数组。作业平台按行接收已核定的 CPU、内存及其他参数。已收到成功回执的行会保留；单行作业失败后重试沿用该行交付编号，便于执行机核对原有克隆任务。

## 绑定环境

1. 选择一台能以 HTTPS 访问 vCenter 的受管执行机，将作业目标固定为这一台。凭据仅授予交付环境及必要资源的权限。
2. 从 `profile.example.json` 复制配置到执行机 `/etc/bklite/vmware/profiles/<profile>.json`。填入实际 vCenter、资源池和目标文件夹的 MoRef、公司 CA，以及经确认的规格、模板、网络和磁盘策略。保持配置与 ITSM 管理员批准的服务目录一致。
3. 让凭据管理或部署工具把 vCenter 密码挂载在 `password_file`，仅执行身份可读。作业参数仅携带业务选项。配置目录由管理员维护，执行机的脚本执行权限应限制为获准使用该 vCenter 交付身份的用户。
4. 在持久磁盘创建 `journal_dir`，仅作业账号可写。多次调用必须使用同一份日志和同一个 vCenter。执行机迁移时一并迁移日志；有待核对交付时保留原资源绑定，防止在其他位置重复创建。
5. 模板需有 VMware Tools、一张网卡及适配的 Linux 初始化规范。分配数据盘时需有可用 SCSI 插槽。脚本支持标准端口组、分布式端口组及单网卡 DHCP，并在批准的 Datastore 上创建 thin 数据盘。操作系统内分区、格式化和挂载由模板的首次启动配置负责。

## 只读检查

下例使用占位的资源 ID，替换为已批准的实际值。该命令连接 vCenter，核查模板、存储可用量、资源池主机连通性、网卡和初始化规范，并在内存中构造克隆请求。它仅执行读取。

```sh
payload=$(python3 - <<'PY'
import base64, json
request = dict(vc_host="vcenter.example.invalid", delivery_id="precheck-1", profile="test", template_id="vm-101", cpu=2,
               memory_gib=4, data_disk_gib=20, network_id="network-21", disk_policy_id="standard")
print(base64.urlsafe_b64encode(json.dumps(request).encode()).decode())
PY
)
python3 provision_vm.py --check "$payload"
```

## 交付与核对

作业成功时最后一行 JSON 包含 `status=success`、交付编号、vCenter 任务号、虚拟机 MoRef、UUID、主机名和 IP。只有已开机、VMware Tools 已运行且回报匹配的主机名和可用 IP 时才确认交付。作业平台的执行号与 vCenter 任务号应分别保留。

`pending` 表示约定的等待时间已到，`unconfirmed` 表示调用或核对未能确认结果，`failed` 表示 vCenter 任务返回失败。以上均以非零状态退出。原编号再次运行时根据日志查原任务及目标虚拟机；重复下发不会发起第二次克隆。若在发送到 vCenter 前后执行机退出且未拿到任务号，需要根据交付编号、固定名称、vCenter 事件和归属标记核对，勿删除日志或改号重跑。

## CMDB 关联入口

有真实交付回执的工单在表单下面提供「查询 CMDB 资产」。只有同时具备工单查看、CMDB 资产查看和目标实例查看权限的用户才可打开链接。查询仅核对本域、本组织的 vCenter 根资产与采集任务，再按 VM MoRef 和交付归属注释匹配。VMware 实例 UUID 是回执字段，与 CMDB 资产 UUID 分别记录。采集尚未覆盖该台 VM、来源不明或归属注释不匹配时显示「待关联」；可在下一轮采集后重新查询，无需重新创建虚拟机。

## 从本地演示切换到真实服务

本地演示使用单独的服务和模拟目录。真实服务先以禁用草稿安装，绑定服务组织和本域审批组。门户申请组可以通过 `--applicant-group` 独立指定。

```sh
python manage.py init_itsm_vmware --profile lab --team 1 --handler-group 1
```

在受管执行机上完成上面的 profile 配置后，使用只读发现命令核实已批准的模板、网络、资源池和 Datastore，导出只含目录与绑定信息的 JSON。下面的环境变量分别代表本地 CMDB 中 vCenter 根资产的 UUID 和作业平台的 Linux 目标 ID。

```sh
python3 discover_vmware_catalog.py /etc/bklite/vmware/profiles/lab.json \
  --export --vc-instance-uuid "$VC_INSTANCE_UUID" --target-id "$JOB_TARGET_ID" \
  --max-quantity 1 > lab-catalog.json
```

将导出的目录交给 BK-Lite 管理员，在 server 环境执行：

```sh
python manage.py init_itsm_vmware --profile lab --team 1 --handler-group 1 --catalog-file lab-catalog.json
```

重复运行会保留已有流程版本和表单配置。作业执行端需要可用的 Job Worker、到执行机的连接和 pyVmomi；ITSM 的 Flowable 外部任务 Worker 需要能调用作业平台模块。完成只读预检后，在流程管理中发布该版本，再启用对应服务。首次验收可限定一台，检查作业平台任务、vCenter 任务、来宾 IP、工单结果和站内通知。
