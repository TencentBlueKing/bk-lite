# 实施方案：CMDB 关联模型属性筛选

依据：[spec.md](spec.md)。交互以已确认的高级筛选样例为准。状态：已按本文实施。

## 接缝

只在这些公开边界上写测试：

1. 条件格式化：默认别名 `n` 的输出与改造前一致；传入别名后作用在节点上。新增运算符 `str!*`、`time<`、`time>`、`empty`、`not_empty`。
2. `advanced_filter` 校验与编译：非法路径、断链、超过 2 跳、原路返回、不可见模型、非法字段、超过 10 条，返回带条件序号的错误。AND 把相同第一跳绑到同一个中间节点；带条件的节点有权限片段，纯中转节点没有。
3. `instance/search`：不传 `advanced_filter` 仍走原列表查询。传入后返回当前模型实例。
4. 导出：未勾选时带上快速搜索和高级筛选；勾选时忽略筛选。条件失效时异步任务失败，不导出全量。
5. FalkorDB 可连接时：写入示例图后按条件查询，覆盖去重、同一对象、前缀绑定、无关联对象、AND/OR。
6. 前端纯函数：条件摘要和请求体。抽屉交互已在样例中确认，不另起浏览器自动化。

## 里程碑

### M1 条件格式化

`graph/format_type.py` 增加运算符。`format_search_params` 增加 `alias`，默认 `n`。别名只替换独立的节点标识 `n`，不改动 `CONTAINS`、`NONE` 等单词。FalkorDB 与 Neo4j 都走这一层。

### M2 校验与编译

新模块 `graph/advanced_filter.py`：

- 校验路径、字段、运算符，最多 10 条，一组内只有 AND 或 OR。
- AND 按第一跳分组成前缀树，组间 `WITH DISTINCT n`。
- OR 按完整路径 `OPTIONAL MATCH`，用 `count() > 0` 合并。
- 查询超时 15 秒，超时返回明确错误。

### M3 列表与导出

- `instance/search` 接收 `advanced_filter`。当前模型权限沿用现有逻辑；条件所在关联节点按其模型权限过滤；纯中转节点不加实例权限。
- 未勾选导出时，同步 `inst_export` 与异步导出任务都带上 `query_list` 和 `advanced_filter`。勾选导出忽略二者。
- 异步任务执行时重新校验。失效则任务失败。

### M4 前端

实例列表快速搜索右侧增加「高级筛选」。筛选范围只决定下一条新条件的层级。关闭抽屉丢弃未应用修改。重置只清草稿。应用成功后关闭抽屉并显示标签，删除标签立即重查。保存方案同时保存快速搜索和高级筛选；失效方案不改变列表。未勾选的「导出全部」带上当前筛选。

## 验证

- `server`：`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_advanced_filter.py apps/cmdb/tests/test_advanced_filter_api.py --no-cov`
- 有 `FALKORDB_HOST` 时同一文件里的真实图用例会执行；没有则跳过，并在交付说明里写明。
- `web`：`pnpm exec vitest run src/app/cmdb/(pages)/assetData/list/__tests__/advancedFilter.test.ts`
