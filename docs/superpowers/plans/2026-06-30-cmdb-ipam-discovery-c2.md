# CMDB IPAM 发现采集 C2 实施计划

## 目标

按 2.7 要求把 IP 发现采集接入现有配置采集链路：子网选择作为任务输入，接入点下发到 NodeMgmt，Telegraf 调 Stargazer，结果进入 VM 后由 CMDB 拉取并回写 IPAM 台账。删除旧 NATS 回调链路。

## TDD 步骤

1. 先补红灯测试：采集对象树出现 `ipam/ip_discovery`；`NodeParamsFactory` 能为 `model_id=ip` 生成标准节点配置；Stargazer `ip_discovery` 插件能从子网推导扫描目标并输出 `ip_info` 数据；CMDB `CollectPluginTypes.IP` 能解析 VM 数据并调用 IPAM 回写服务。
2. 逐步实现绿灯：常量注册、IPAM NodeParams、Stargazer 扫描器标准化、CMDB IP 采集插件、回写服务抽取。
3. 删除旧链路：移除 `maybe_dispatch_ip_discovery`、RPC `dispatch_ip_discovery`、Stargazer `ip_scan` NATS handler、CMDB `receive_ip_discovery_result`。
4. 验证：运行新增/受影响的 server 与 stargazer 测试；完成前按 `verification-before-completion` 做新一轮验证。

## 边界

- 仅改 IPAM 发现采集相关文件。
- 不新增独立 IP 表，回写继续使用 CMDB 模型实例。
- 手工记录不被自动发现覆盖。
- 不保留旧 NATS 影子入口。
