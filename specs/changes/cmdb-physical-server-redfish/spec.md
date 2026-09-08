# CMDB 物理服务器 Redfish 配置采集

Status: implemented

## 目标

在现有“物理服务器 SSH”和“物理服务器 IPMI”旁新增“物理服务器 Redfish”入口，
通过 BMC HTTPS API 只读采集物理服务器基础身份字段，并写入同一个
`physcial_server` 模型。

## 已锁定的产品决定

- SSH、IPMI、Redfish 均以本次采集目标 IP 构建 `physcial_server.inst_name`。
- 同一实例继续使用现有 `collect_task` 过滤和实例名唯一校验；不新增抢占、释放、迁移
  或并发所有权协议。
- 上述规则只在三种任务填写相同目标 IP 时合并实例。SSH 操作系统 IP 与 BMC 管理 IP
  不同时，仍会形成两个实例；首版不新增序列号关联或人工绑定。
- Redfish 直接开放，不增加 Agent 能力门控或独立诊断工具。
- Redfish 固定使用 HTTPS Basic Auth，默认 `verify_tls=true`。首版不支持上传或选择 CA；
  用户可在受信任管理网络中显式关闭证书校验，界面必须提示中间人风险。
- 首版只采集唯一 `ComputerSystem` 的整机基础身份，不采集 OEM 扩展，也不创建
  memory、disk、nic、gpu 子实例。

## 调用链

`RedfishTask` → `CollectModelSerializer` → `PhysicalServerIPMINodeParams` → Stargazer
请求构建与凭据尝试 → `PhyscialServerProtocolInfo` → `PhyscialServerRedfishInfo` →
物理服务器 protocol formatter → `collect_task` 过滤与 CMDB 实例写入。

## 凭据与协议契约

- `collection_protocol` 只允许 `ipmi`、`redfish`；历史 protocol 任务缺少该字段时按
  IPMI 兼容。
- Redfish 凭据字段为 `username`、`password`、`port`、`verify_tls`；IPMI 额外使用
  `privilege`。端口范围为 1～65535，凭据池最多 3 组。
- 多凭据按界面顺序下发并逐组尝试；密码只通过环境变量引用传递。
- Redfish 服务根使用规范 URI `/redfish/v1/`，不跟随 HTTP 重定向；服务返回的
  `@odata.id` 必须仍位于同一目标的 `/redfish/v1` 命名空间。
- 默认采集阶段的证书校验失败必须收敛为稳定错误码 `tls_validation_failed`，不得只
  返回通用采集失败。

## 兼容与影响

- 不修改实例模型、数据库结构或存量资产。
- 物理服务器 protocol 多凭据修复同时作用于 IPMI 和 Redfish；其他 NodeParams
  子类不受影响。
- 任务名称接口必须根据 `driver_type + collection_protocol` 返回
  `physcial_server`、`physcial_server_ipmi` 或 `physcial_server_redfish`，保证资产详情
  跳转到正确插件。

## 验收

- Server：协议与凭据边界校验、IPMI/Redfish 多凭据下发、历史 IPMI 默认行为、任务
  名称和插件路由。
- Agent：规范服务根、同源资源限制、唯一 ComputerSystem、TLS 开关、正式采集阶段
  TLS 错误分类和响应大小上限。
- Web：Redfish 创建/编辑/复制时 TLS 默认值与显式关闭语义、类型检查和 lint。
