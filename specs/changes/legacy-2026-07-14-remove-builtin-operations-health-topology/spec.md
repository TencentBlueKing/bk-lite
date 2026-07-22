# Historical Superpowers change: 2026-07-14-remove-builtin-operations-health-topology

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-14-remove-builtin-operations-health-topology-design.md

## 背景

运营分析当前从 `server/apps/operation_analysis/support-files/builtin_canvases.yaml` 导入 `topology::运营健康拓扑_内置`。该拓扑不再作为系统内置内容提供。

## 目标

- 从内置画布 YAML 中完整删除 `topology::运营健康拓扑_内置` 条目。
- 不增加禁用开关、过滤逻辑、数据库迁移或即时数据库操作。
- 下次执行 `init_builtin_canvases` 或 `batch_init` 时，沿用现有“先删除旧内置画布、再按 YAML 重建”的流程清理数据库中的旧内置拓扑。

## 实现范围

1. 删除该拓扑的 `key`、元数据、节点、边、过滤器和引用配置。
2. 在内置画布测试中增加回归断言，确认 YAML 不再包含该 key。
3. 保留其他内置拓扑、仪表盘、大屏、数据源和命名空间不变。

## 验证

- YAML 可被安全解析。
- `topologies` 中不存在 `topology::运营健康拓扑_内置`。
- `server/apps/operation_analysis/tests/test_init_builtin_canvases.py` 相关测试通过。

## 非目标

- 不修改内置画布加载命令的删除和导入语义。
- 不直接连接或修改现有部署的数据库。
- 不影响用户自行创建的同名拓扑。
