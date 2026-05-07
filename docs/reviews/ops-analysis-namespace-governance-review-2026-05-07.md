# 运营分析 NameSpace 全局化治理债务

## 问题本质

当前运营分析的 `NameSpace` 已经退化成“全局共享的 NATS 凭据与路由对象”，不再带组织边界。任何拥有 `namespace-*` 菜单权限的用户，看到和修改的都是同一张全局表；导入导出链路也按全局名称解析依赖，而不是按组织范围解析。这意味着数据源虽然有 `groups` 字段，但其下游实际使用的 NATS 连接并不受组织约束。

## 仓库证据

- [`server/apps/operation_analysis/migrations/0010_remove_namespace_groups.py`](/Users/umaru/.codex/worktrees/bklite-15-ops-analysis-review/server/apps/operation_analysis/migrations/0010_remove_namespace_groups.py) 直接删除了 `NameSpace.groups`。
- [`server/apps/operation_analysis/models/datasource_models.py`](/Users/umaru/.codex/worktrees/bklite-15-ops-analysis-review/server/apps/operation_analysis/models/datasource_models.py) 中 `NameSpace` 只剩 `name/account/password/domain/namespace` 等连接字段，没有任何组织字段。
- [`server/apps/operation_analysis/views/datasource_view.py`](/Users/umaru/.codex/worktrees/bklite-15-ops-analysis-review/server/apps/operation_analysis/views/datasource_view.py) 的 `NameSpaceModelViewSet` 直接基于 `NameSpace.objects.all()` 暴露列表、详情、增删改，没有走 `AuthViewSet` 的实例/组织过滤。
- [`server/apps/operation_analysis/services/import_export/precheck_service.py`](/Users/umaru/.codex/worktrees/bklite-15-ops-analysis-review/server/apps/operation_analysis/services/import_export/precheck_service.py) 中 `_check_group_permission()` 对没有 `groups` 字段的对象直接返回 `True`，导致命名空间冲突和覆盖天然按“全局可见”处理。
- [`server/apps/operation_analysis/services/import_export/export_service.py`](/Users/umaru/.codex/worktrees/bklite-15-ops-analysis-review/server/apps/operation_analysis/services/import_export/export_service.py) 导出命名空间时直接 `NameSpace.objects.get/filter(...)`，并把 `account/password/domain` 打包进 YAML；一旦某组织导出的数据源依赖了共享命名空间，就会把全局连接配置一并带出。

## 影响范围

- 不同组织的数据源会复用同一批 `NameSpace` 记录，绑定关系无法表达“这个 NATS 连接只允许被哪个组织使用”。
- 命名空间重名冲突、导入覆盖和 YAML 依赖解析都是全局语义，容易把一个组织的数据源误绑定到另一个组织维护的连接配置。
- 导出数据源时会连带导出其引用的 `NameSpace` 凭据配置，扩大跨组织泄露风险。

## 为什么暂不直接修复

这不是单点补丁问题。要真正收敛风险，至少需要同时恢复 `NameSpace.groups`、补历史数据迁移、把 `NameSpace` 视图切到组织权限模型、重写导入导出冲突判定与依赖解析规则，并补上现有全局数据的归属修复策略。单轮内直接回滚这套模型，风险会高于本次 runtime 口子的最小修复。

## 建议后续处理

1. 恢复 `NameSpace.groups`，并把 `NameSpace` 全量切回组织作用域对象。
2. 导入导出链路改为“同组织内按业务键解析”，不再用全局 `name` 直接命中。
3. 为已有全局 `NameSpace` 制定一次性归属迁移方案，再开放后续编辑与覆盖。
