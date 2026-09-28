# CMDB 实例导出性能修复

## 范围与原因

资产页面 `inst_export` 在关联写行时逐实例读取图库；正常无关联也触发全部
`instance_association` 读取。实例列表与普通 openpyxl 工作簿同时全量驻留内存。

本次实施关联查询、元数据按需加载、同步导出容量三个阶段。保留已选择、当前页、
全部三种范围；“全部”仍表示当前模型授权范围内全部实例，不新增页面筛选语义或异步任务。

## 实现决定

- `InstanceManage.inst_export` 负责授权范围、分批查询及关联结果准备；
  `Export.append_inst_list` 只格式化并写入一批数据，不执行逐实例图库查询。
- 实例按不可变 `inst_uuid` 升序，每批 500 条；下一批用严格大于游标条件，不使用 offset。
  每批重复应用组织和实例级权限；空权限范围不查询实例。只投影选中的属性及身份字段。
  已选择实例的前置存在性校验仅读取身份字段，仍拒绝缺失或重复 UUID。
- 与过去内部节点 ID 排序相比，导出行顺序改为 UUID 升序；字段顺序保持用户所选顺序。
  导出是运行期分批读取，不提供跨批次数据库快照：并发修改可能反映在后续批次，
  新增实例是否被纳入取决于 UUID 与当前游标的位置，已删除实例不再输出。
- 关联查询从本批次实例节点出发，分别读取入向、出向所选关系；每批两次图查询。
  从实际端点取得模型和 UUID，兼容边缺少冗余端点属性，不保留全图读取回退。
  按实例 UUID 与边 ID 去重自环；不同边的同名对端保留。模型可见性按本次导出的关联定义复用。
- 元数据在用户/组织选项扩充前按所选属性过滤；没有选择关联时不加载关联定义。
- 实例工作簿使用 write-only 顺序写入；模板下载继续使用普通工作簿。
  保持三行表头、枚举辅助表、校验规则与样式，附件/图片字段在表头和数据行一致排除。
- 页面下载保存至临时文件，`FileResponse` 传输；ASGI 使用异步分块迭代，避免 Django
  将同步迭代器全部收集成列表。生成失败、响应关闭、迭代结束清理对应文件。
  场景视图继续通过默认的 BytesIO 接口合并工作簿。
- 成功时只记录一条有界耗时汇总，包含元数据、实例、关联、Excel 及总耗时。
  不记录实例内容、UUID 列表和请求正文；失败继续抛给已有上层异常边界。

## 验证与运行限制

- 服务回归：导出文件内容、1/500/501/1001 条查询预算、无关联、入向、自环、
  同名对端、未选关联、双组织范围、跨批删除、空权限、写入失败资源清理。
- 图库适配器回归：端点查询、字段投影、字符串游标、权限条件参数绑定，覆盖两种驱动。
- Excel/视图回归：样式、枚举校验、现有字段类型、WSGI/ASGI 分块下载和关闭行为。
- 真实图库测试：显式提供 `CMDB_EXPORT_TEST_FALKORDB_URL` 后运行
  `apps/cmdb/tests/test_export_graph_integration.py`，仅创建并清理独立随机测试图。
  验证旧边属性缺失、双向关系、投影、分页、组织条件及 UUID 索引执行计划。
  本机未运行真实图库测试；不能把模拟查询预算当作线上响应时间证明。
- UUID 索引复用既有 UUID 迁移机制，本次不修改启动编排或自动添加索引。
- 本地 1 万行 × 30 个字符串字段的独立进程测量：顺序写入前约 2.005 秒、
  额外峰值内存 108.9 MB；之后约 1.704 秒、0.3 MB。
  该结果只衡量 Excel 写入，不包含真实数据库、网络和部署环境。
- 仍为同步生成，生成完才返回响应，前端代理 60 秒超时保持现状。
  关系返回量仍受本批实例的实际关联度影响；大规模任务和总量限制需结合部署压测单独评估。

## 测试环境已知问题

- 默认 SQLite 迁移失败：`NewSessionEventRelation has no field named 'event'`。
  本次采用 `--nomigrations` 验证模型及功能，不改该迁移。
- 扩大回归发现现有 UUID 大小写断言、导入组织夹具及场景视图旧 mock 参数失败；
  已用 HEAD 原始对应实现复核，不纳入本次性能修改。

## 本次验证记录

- 相关回归分批共 155 个不同测试用例通过；真实图库集成测试 1 项因未配置连接跳过。
  扩大回归中的既有失败单独复核，不计入通过数。
- 本次新增/修改的可执行行覆盖 185/185；这是差异行覆盖，不代表整个 CMDB 的覆盖率。
- 提交钩子格式化并清理测试的未使用导入后，重新验证 94 项通过、1 项真实图库测试跳过；
  排除已记录的导入组织夹具及关联约束组共 8 项。输出见 `/tmp/cmdb-export-precommit-tests.log`。
- `git diff --check` 通过。原始测试输出保存在本次会话的
  `/tmp/cmdb-export-final-tests.log`、`/tmp/cmdb-export-additional-tests.log`；
  基线证据为 `/tmp/cmdb-export-baseline-test.log`、`/tmp/cmdb-export-baseline-uuid.log`、
  `/tmp/cmdb-export-baseline-views.log`。

核心回归命令（在 `server/` 下）：

```bash
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  .venv/bin/python -m pytest \
  apps/cmdb/tests/test_instance_export_service.py \
  apps/cmdb/tests/test_export_graph_adapters.py \
  apps/cmdb/tests/test_export_helpers.py \
  apps/cmdb/tests/test_import_asso_export.py \
  -o addopts='' --nomigrations --no-cov -q
```

真实图库验证需由环境注入专用测试连接后执行同样命令，将测试路径换成
`apps/cmdb/tests/test_export_graph_integration.py`。该测试会在独立随机图中写入夹具并清理。

## 回滚

只回滚本次应用代码，无数据或数据库结构迁移。保留既有 UUID 数据及索引。
回滚会恢复旧导出的逐实例查询与内存开销。
