# 01 — 布局配置落盘与刷新回填

Status: done

Blocked by: None

**What to build:** 网络状态拓扑组件实例能携带并保留布局几何配置；已有保存几何时，刷新后按覆盖规则渲染，而不是每次只用算法布局。手工几何按 `layoutMode` 分桶。

- [x] 组件实例配置支持 `layoutMode`、`layoutByMode`（每桶含 `nodePositions` / `linkVertices`；新建缺省 `hierarchical`；打开时恢复上次 `layoutMode`）
- [x] 渲染时先按当前 `layoutMode` 算法布局，再应用该 mode 桶内仍存在的节点位置；该桶内用户 `linkVertices` 优先于自动并行边偏移
- [x] 切换布局模式只换并持久化当前 mode，不丢其它 mode 几何；无确认弹窗；再次打开恢复上次模式
- [x] 配置弹窗提交不会冲掉已有布局字段
- [x] 仪表盘/大屏页面保存后，刷新能回填并按保存几何与上次布局模式渲染
- [x] 有针对布局覆盖、分桶隔离与配置透传的行为测试（纯函数/提交合并接缝）

## Completion evidence

- `utils/networkStatusTopologyLayout.ts` + unit tests
- `submitConfig` + `widgetConfig` 合并保留 `layoutByMode`
- widget 渲染应用当前 mode 桶位置覆盖与手工折点优先
