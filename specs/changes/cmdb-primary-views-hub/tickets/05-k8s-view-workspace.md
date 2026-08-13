# 05 — K8S 视图工作台

Status: done

Blocked by: 02 — 实例选择器、记忆与空态

**What to build:** 一级「K8S 视图」复用集群资源详情能力；选择器仅 `k8s_cluster`；查看详情进基础信息。

- [x] 仅 k8s_cluster 可选；选中后展示与详情「资源详情」同能力面
- [x] 组件不再只能作为详情 page 硬读 searchParams（可被工作台注入集群上下文）
- [x] 「查看详情」进入该集群实例基础信息

## Completion evidence

- `ViewCanvasHost` `viewType === 'k8s'` 渲染 `K8sResourceDetailsContent instId={focus.inst_id}`
- 资格仅 `k8s_cluster`：`test:cmdb-views-hub-core` PASS；`test:cmdb-k8s-resource-overview` PASS
- `buildViewsPathPreserving` 保留 K8S UI query（sub / expanded_workloads 等）：core 断言覆盖
- Shell「查看详情」→ `buildBaseInfoPath`；hub wiring PASS
