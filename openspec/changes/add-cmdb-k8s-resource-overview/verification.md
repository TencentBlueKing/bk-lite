# 验证记录

日期：2026-07-10

## 已通过

- 后端相关回归：22 个测试通过，覆盖 K8S 概览服务、只读 actions、关联实体缺字段、枚举列表值和既有应用资源概览。
- 补充关联实体缺少 `model_id` 的回归场景：Workload 仍通过 `Cluster → Namespace → Workload` 关联元数据正确进入详情列表。
- 连接 FalkorDB 实例 `278` 验证：真实 `workload_type` 为 `['deployment']`；归一化后 Deployment 12 条、其他工作负载 0 条。
- 新增后端代码覆盖率：82%（service 82%，serializer 82%）。
- 前端定向 ESLint：新增页面、拓扑、详情菜单接线和 Storybook 故事无错误。
- 前端行为/契约测试：`pnpm test:cmdb-k8s-resource-overview` 通过，覆盖工作负载、Pod、Node 独立导航分组，资源列表复用 `CustomTable`、small 密度、禁用选择和字段设置，以及实例菜单顺序、单滚动高度链和名称新标签页属性。
- TypeScript 定向检查：全量输出中没有 `k8sResources` 或新增故事相关错误。
- Storybook 静态构建：通过；除既有 1440px 概览走查外，新增只读资源列表故事并完成视觉复核，确认五列完整展示、资产列表式工具栏、表格密度和底部分页正常。
- 实际实例 `278` 浏览器回归：一级菜单依次为「基础信息」「资源详情」「关联关系」；列表内容区、Spin、资源列表和表格剩余区形成 756/672/672/628px 的连续高度链，页面不存在外层纵向滚动容器；名称链接具有 `target="_blank"` 和 `rel="noopener noreferrer"`，点击后新增基础信息标签页且原列表 URL 保持不变。
- DIV 拓扑契约：概览不再引用 `Descriptions` 或采集事实文案，拓扑不再引用 `NetworkTopologyX6Canvas`、缩略图或画布控制；纯函数测试覆盖真实节点优先排序、缺失端点忽略、SVG 贝塞尔路径，以及 Workload 聚焦只包含祖先链和自身后代、不扩散到兄弟分支。
- Storybook 长列视觉回归：12 条完整五层链生成 48 条 SVG 关系线；唯一共享滚动容器可视高度 518px、内容高度 954px，横向 `scrollWidth` 与 `clientWidth` 相等，采集事实不存在且 X6 节点数为 0。
- 实际实例 `278` DIV 概览回归：采集事实不存在，渲染 22 个 DOM 节点和 22 条 SVG 关系线，X6 节点数为 0；五列无横向溢出，拓扑使用单一内部纵向滚动。Storybook 中节点聚焦正确降级无关节点和关系线，右键与 `Shift+F10` 均打开同一只读菜单。
- OpenSpec：`openspec validate add-cmdb-k8s-resource-overview --strict` 通过。

## 仓库基线阻断

- `pnpm lint` 仍被本次变更之外的既有错误阻断，包括告警、变更记录、监控查询和大量旧 Storybook renderer import；新增文件定向 lint 已通过。
- `pnpm type-check` 仍被本次变更之外的告警、CMDB 自动发现和 OpsPilot 类型错误阻断；输出中没有本次新增文件错误。
- 当前后端虚拟环境未安装 `black`、`isort`、`flake8`，无法执行对应样式门禁；已执行 Python compileall 和相关 pytest。
- 后端全量 pytest 收集到 19,072 个用例后，被 120 个既有收集错误中断；主要原因是当前启用应用集合未包含 `job_mgmt`、`log`、`mlops`、`opspilot`，但对应测试仍导入其 Django 模型。
- 真实采集集群、超过 50 Pod 的线上 Workload、部分权限账号不在当前本地环境中，因此任务 5.1–5.4 和最终真实账号联调保持未完成。
