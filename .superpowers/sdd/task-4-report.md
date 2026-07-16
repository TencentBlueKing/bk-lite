# Task 4 实施报告

## 结果

- CMDB 后台节点查询每一页强制携带 `skip_permission=True`，调用参数不能覆盖系统身份。
- 节点管理真实响应合同保持 `{"count", "nodes"}`，未采用计划示例的 `data.items`。
- 页大小硬上限为 500，页数硬上限与默认值均为 100；预算耗尽抛 `NODE_PAGE_LIMIT_EXCEEDED`。
- 查询在 `deadline_at` 到期前停止 RPC 并抛 `NODE_QUERY_TIMEOUT`。
- RPC/异常响应仅外显稳定码与异常类型摘要（最长 255 字符），日志不记录原始异常详情或节点数据。
- NodeService 普通无权限/组织上下文查询仍保持 fail-close，生产代码未修改。

## TDD 与验证

- RED：7 个预期行为失败（缺系统身份、页大小上限、max_pages/deadline、异常脱敏）。
- GREEN：`helpers + resilience + b75 NodeService` 首轮 70 passed。
- 最终回归：上述集合加 Task 2 reconciler、Task 3 views/models，共 118 passed。
- 覆盖率：coverage JSON 与 `git diff --unified=0` 交叉核验，生产新增可执行行 35/35，增量覆盖率 100%；service 全文件为 70%。
- 静态检查：`py_compile`、`isort --check-only`、`git diff --check` 通过，新增行 flake8 命中 0。
- 已知基线：整文件 black 会格式化三个历史文件；flake8 仅报告 service 既有 E125 与 resilience 既有 E501，未做超范围格式化。
