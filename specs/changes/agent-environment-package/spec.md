# 环境安装包

目标：管理员导出环境专用单文件；同一包可在多台空白 Linux x86_64 主机上执行，各自注册；重复执行不重装、不新增节点。

范围：Linux x86_64、systemd。不覆盖未知既有安装，不删除测试资源。Windows 与其他架构不在本能力内。

## 契约

- 机器接口只有两条统一网关端点：POST node-mgmt/environment-install、POST node-mgmt/environment-install-status。安装服务再次核对授权哈希、创建者、组织、区域、固定包摘要/版本、有效期和额度。
- 先锁云区域再锁授权。同一 request_id 幂等，字段变化拒绝。同一主机重复执行沿用已保存的节点身份，不重复占用额度。节点删除后不允许旧授权静默重建。
- 首次心跳验证固定归属、install_id 和素材摘要回执。真实心跳使用单独的 last_heartbeat_at。
- 管理接口使用节点 Edit 权限，并校验当前组织。页面入口使用 InstallController，与「安装控制器」按钮一致。提供导出、本人授权列表、吊销和安装记录。
- 导出预检失败返回稳定 error_code，不返回文件路径、证书正文或令牌。区分 package_digest_missing、ca_invalid、install_script_invalid，其余为 export_precheck_failed。
- 安装令牌的 created_by 只保存创建者用户名的前 32 位。授权记录保存完整创建者，后续核对使用授权上的创建者。
- 新环境包把短期会话令牌放在安装器本地文件中，官方安装器改用请求头传递。旧安装仍接受查询参数。
- 不选额外组件时仍自动安装 NATS Executor。选中的组件写入授权和签名清单。新环境注册只分配这些默认配置。
- 组件健康以新鲜心跳状态 0 为准。心跳要在最近 2 分钟内，并且不早于建档时间。NATS Executor 还要通过 RPC 就绪检查。心跳已是 0 但 RPC 未就绪时，保留注册，安装退出 70，并可重试。
- 管理端安装记录区分待安装、已建档但组件未就绪、成功、失败（阶段）。结果接口用同一条新鲜心跳规则判断组件健康，并返回 executor_rpc_ready。心跳过期时不显示成功。安装过程中的逐阶段上报不在本版。
- 安装空间由管理员填写。平台 CA 来自当前云区域配置，页面不手填。
- 迁移编号为 node_mgmt 0050，依赖 0049_collector_default_backfill。正式发布私钥只由发布环境挂载，不提交源码。构建说明见 agents/environment-installer/README.md。

实机证据和临时环境记录见配套 PR 描述，不写入本规格。
