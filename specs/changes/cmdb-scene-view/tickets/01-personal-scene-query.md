# 01 — 跨模型标签活查询 + 个人场景存取

Status: done

Blocked by: None

**What to build:** 能把「模型范围 ∩ 标签（AND/OR，默认 AND）」存成个人场景，并按打开者实例权限执行活查询：返回匹配总数、按模型数量、各模型实例页；count 为 0 的模型不出现在结果里。无标签字段或打不上标签就是 0 条，不返回原因。

- [x] 个人场景可创建、读取、更新、删除；默认可见范围为个人；标签匹配默认 AND
- [x] 执行结果按打开者权限过滤，与资产列表同一套组织/创建人规则
- [x] AND 必须同时命中全部所选标签；OR 命中任一标签
- [x] 某模型 0 条则该模型不出现在 `models` 列表；`total` 为各模型 count 之和
- [x] 读/写个人场景与执行需要 `asset_info-View`；他人个人场景不可见
- [x] 服务层与 API 测试覆盖 AND/OR、权限参数传入、空模型省略、个人隔离

## Notes

- 场景是新对象，不要写入 user_configs。
- 逐模型复用现有实例列表查询，不要新造图查询 DSL。
- 组织共享与全局字段可以落在模型上，但本票只允许创建/改个人场景；其它可见范围的写入留给 03。

## Completion evidence

- 查询服务与 API 接缝测试 28 passed：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_scene_view_query_service.py apps/cmdb/tests/test_scene_view_views.py --no-cov`
- 模型 `SceneView`、迁移 `0051_sceneview`、`/cmdb/api/scene_views/`（含 `execute`）
- 本机 sqlite `--reuse-db` 全量 migrate 会撞上既有的 `NewSessionEventRelation.event` 问题，故 API 测试不落库；查询语义与权限/日志在单元接缝锁定
