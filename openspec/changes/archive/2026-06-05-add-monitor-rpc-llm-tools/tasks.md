## 1. Monitor 工具公共层

- [x] 1.1 新增 `server/apps/opspilot/metis/llm/tools/monitor/` 目录及 `__init__.py`、`utils.py` 基础结构
- [x] 1.2 在 `monitor/utils.py` 中实现账号密码校验与组织解析，统一获取用户对象和默认/显式组织信息
- [x] 1.3 在 `monitor/utils.py` 中封装 `MonitorOperationAnaRpc` 调用入口，统一组装 `user_info` 和通用错误/成功返回结构

## 2. 监控查询工具实现

- [x] 2.1 在 `monitor/objects.py` 中实现监控对象发现工具，并通过 RPC 调用下游 Monitor NATS 接口
- [x] 2.2 在 `monitor/objects.py` 中实现监控对象实例查询工具，并使用账号密码校验后的用户与组织参数发起 RPC 查询
- [x] 2.3 在 `monitor/metrics.py` 中实现对象级指标发现工具，并通过 RPC 返回可查询指标列表
- [x] 2.4 在 `monitor/metrics.py` 中实现实例级指标发现工具，并支持基于实例筛选指标
- [x] 2.5 在 `monitor/metrics.py` 中实现指标数据查询工具，并支持时间范围、实例和维度参数透传
- [x] 2.6 在 `monitor/alerts.py` 中实现活跃告警查询工具，并支持常见过滤条件透传
- [x] 2.7 在 `monitor/alerts.py` 中实现历史告警异常段查询工具，并支持时间范围和过滤条件透传

## 3. 工具注册与元数据接入

- [x] 3.1 在 `monitor/__init__.py` 中汇总导出监控工具函数与构造参数元数据
- [x] 3.2 更新 `server/apps/opspilot/metis/llm/tools/tools_loader.py`，注册 `monitor` 工具类别并确保 `langchain:monitor` 可被发现
- [x] 3.3 更新 `server/apps/opspilot/services/builtin_tools.py`，将 `monitor` 作为新的内置工具类别暴露，并生成子工具元数据

## 4. 验证

- [x] 4.1 检查监控工具在缺少用户上下文、参数不完整和 RPC 异常时返回明确错误信息
- [x] 4.2 验证监控工具不会直接调用 `apps.monitor` 本地实现，而是统一通过 `MonitorOperationAnaRpc` 发起请求
- [x] 4.3 执行受影响模块的最小验证命令，确认工具加载与静态检查通过
