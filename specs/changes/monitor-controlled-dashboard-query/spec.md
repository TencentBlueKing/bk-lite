# 监控看板受控查询与原始 PromQL 入口退役

## 状态

- Issue：`#4820`
- 决策：采用方案 A，迁移现有调用方并删除原始 PromQL REST 入口。
- 产品约束：不保留“管理员任意执行 PromQL”的兼容能力。
- 部署介入：不需要新增环境变量、迁移脚本或运维配置。

## 背景

监控 Web 曾将看板内置 PromQL 直接提交到
`metrics_instance/query`、`metrics_instance/query_range`。后端只负责转发查询，无法从请求中
可靠推导监控对象、实例范围和当前用户可见实例，因此页面权限与 VictoriaMetrics 查询范围
可能不一致。

此前 Search、Mobile 和运营分析调用方已经迁移到受控指标查询，NATS/RPC 的原始
`mm_query`、`mm_query_range` 处理器也已退役。本变更完成剩余 Web 看板迁移并删除 REST
原始查询入口。

## 行为规格

### 请求契约

- 范围查询与即时查询统一使用既有 POST 入口：
  `query_by_metric_range`、`query_by_metric`。
- 请求必须且只能提供 `metric_id` 或 `capability_id` 之一，不能提交 `query`。
- 请求必须携带 `monitor_object_id` 和非空 `instance_ids`；服务端按当前用户、当前团队及
  `include_children` 计算实例权限，任一实例越权时整次请求失败且不访问 VictoriaMetrics。
- `metric_id` 查询只允许使用服务端指标模板，并只接受指标声明过的筛选维度和固定汇聚方式。
- `capability_id` 查询只允许使用仓库生成的看板能力清单；能力必须与监控对象绑定，且每个
  PromQL 选择器都必须包含由服务端注入的 `__$labels__` 实例占位符。
- 服务端根据已授权实例生成标签匹配条件，根据请求时间范围生成 `__$window__`；浏览器不能
  覆盖模板、实例匹配条件或窗口表达式。
- Kafka 消费位点等有限动态查询只接受结构化维度参数，最多 10 组；服务端转义标签并生成
  固定查询形状。
- 主机详情中的进程视图使用 `host_process` 受控作用域：先校验父级 Host 实例权限，再由
  服务端生成主机和进程名匹配条件；最多接受 100 个进程名。

### 能力清单

- `web/scripts/generate-monitor-query-capabilities.ts` 从内置看板配置和查询模块生成静态清单。
- 能力 ID 由模板稳定计算；生成阶段拒绝 ID 冲突，服务端加载阶段重新校验 ID、模板长度、
  对象绑定和实例占位符。
- 修改内置看板查询时必须重新生成清单；`--check` 模式用于 CI/评审验证清单没有过期。
- 清单是查询模板的服务端允许列表，不是用户输入或运行期配置。

### 兼容与退役

- 删除 `MetricsInstanceViewSet` 的 GET `query`、`query_range` action；旧 URL 不提供兼容转发。
- Web 看板、搜索页和指标视图不再发送原始 PromQL。
- 不恢复 NATS/RPC 的 `mm_query`、`mm_query_range`，也不保留仓外 NATS 调用兼容。
- 运营分析中指向上述路由的历史自定义数据源保留记录以便识别，但禁止执行、保留原路由的
  编辑及再次导入；用户仍可删除记录或将其改为受支持的数据源。历史内置数据源由既有
  `init_builtin_canvases` 退役流程清理。
- 历史内置看板保持原图表语义、单位换算、时间步长和缺口检测行为。

## 安全与失败语义

- 普通用户与管理员执行同一实例范围校验流程；超级用户只跳过权限规则过滤，仍必须提交真实
  监控对象和实例，且不能执行任意 PromQL。
- 未认证上下文、未知能力、对象不匹配、实例越权、原始 `query`、非法动态维度及非法时间
  参数均在访问 VictoriaMetrics 前失败。
- 查询能力不接受客户端自定义筛选或汇聚；需要新查询形状时必须通过仓库代码和能力清单评审。
- 本变更不记录查询正文、身份凭据或 VictoriaMetrics 响应正文。

## 验收要点

1. 现有 Monitor Web 看板正常加载，浏览器请求体不含 `query`。
2. 同一能力只能查询当前用户在当前团队可见的目标实例。
3. 混入任一越权实例时整次请求失败，VictoriaMetrics 调用次数为零。
4. 能力与监控对象不匹配、能力不存在或能力参数非法时调用次数为零。
5. Kafka 动态维度中的引号和反斜杠被安全转义，且不能改变查询结构。
6. 旧 REST `query`、`query_range` action 不再注册。
7. Web、Mobile、运营分析和 NATS/RPC 中不存在对退役原始入口的调用。
8. 生成器 `--check`、Web 类型检查、前后端聚焦测试通过。

## 测试接缝

- `AuthorizedMetricQueryService`：指标/能力二选一、原始查询拒绝、实例授权、对象绑定、
  `host_process` 和查询参数转发。
- `dashboard_query_capabilities`：清单完整性、模板渲染、Kafka 维度转义和限制。
- `MetricsInstanceViewSet`：认证上下文、成功响应、越权失败和旧 action 退役。
- Web 查询参数：能力 ID 稳定、静态及动态请求均不携带原始 PromQL。
- 静态调用扫描：旧 REST 路径与 `mm_query`、`mm_query_range` 调用归零。
