# Historical Superpowers change: 2026-06-17-opspilot-remove-knowledge-base

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## verifications: 2026-06-17-opspilot-remove-knowledge-base-verification.md

- 日期: 2026-06-17
- 分支: `claude/bold-tu-40b23d`
- 状态: **该功能暂不合入 master**;所有改动仅保留在本分支(未 push、未合并 master)

## 1. 范围回顾
删除 OpsPilot 知识库功能,含知识图谱(graph_rag)、问答对(qa_pairs),以及技能/智能体上依赖知识库的全部 RAG 能力。设计与计划见:
- spec: `docs/superpowers/specs/2026-06-16-opspilot-remove-knowledge-base-design.md`
- plan: `docs/superpowers/plans/2026-06-16-opspilot-remove-knowledge-base.md`

## 2. 分支提交
- `e7b71e00c` feat(opspilot): 删除知识库功能（含图谱、问答对）及技能 RAG 能力
- `ca198aa0a` Merge branch 'master' into claude/bold-tu-40b23d（合入当时 master HEAD `8654f9b3a`,领先基线 61 个提交）
- `8ecb13252` test(opspilot): 删除知识库后的测试收尾

## 3. 合并 master 的冲突处理(2 处,均已解决)
- **代码冲突 `server/apps/opspilot/viewsets/history_view.py`**:master 新增租户隔离安全过滤 `bot__team__contains=[current_team]`;本分支删除了 `citing_knowledge` 列。解决为**两者都保留**:保留安全过滤 + 去掉已删列。
- **迁移冲突**:两个 `0057` 叶子节点(本分支 `0057_remove_fileknowledge_...` 删知识库表 / master `0057_workflowtaskresult_is_test` 加 `is_test` 列)→ 生成合并迁移 `0058_merge_20260617_1654.py`(两迁移触及不同表,无操作冲突)。

## 4. 验证结果

### 4.1 后端(用项目 venv 实跑)
- `manage.py check`:System check identified no issues。
- `makemigrations --check`:No changes detected(模型与迁移图一致)。
- 聊天链断言:`graph.py` 链路已无 `naive_rag_node`,入口边改为 `user_message_node`。

### 4.2 回归对比(干净顺序跑,无并发、独立 test DB)
| | failed | passed |
|---|---|---|
| 当前 master(`8654f9b3a`) | 297 | 485 |
| 合并后本分支(收尾后) | ~283 | 442 |

- 整套 ~283–297 失败是该套件**固有的串行污染基线**(单文件隔离跑全过),master 与本分支同源,非本次引入。
- 失败集差集(本分支独有、master 没有的**真实测试**失败):收尾前 2 个 → **收尾后 0 个**。

### 4.3 收尾的 2 个测试(均为删除的预期副作用,非功能回归)
- `react_agent/cases/test_llm_exception_swallowed.py::test_return_shape_differs_from_success`:该测试**按硬编码行号**读 `chat_service.py`,删除 RAG 后 `invoke_chat` 的 except 块上移导致读错区间;代码本身正确(仍返回 `success=False`+`error`)。已把行号区间修正到 136–158。修正后该文件 `2 failed, 6 passed`,**与 master 完全一致**(剩余 2 个是 bug #2853 的文档型测试,master 上也挂)。
- `tests/test_nats_api_module_data.py::test_known_module_knowledge_succeeds`:断言已删除的「knowledge」nats 模块可用,预期失败。已移除该用例及其 `KnowledgeBase` stub;该文件现 **9 passed 全绿**。同文件其余模块用例全过,说明 nats_api 对其他模块无副作用。

### 4.4 前端(静态)
- opspilot 作用域 `pnpm type-check`:**无任何知识库相关类型错误**(残余仅为该 worktree 借用依赖的环境问题,见 `[[worktree-web-frontend-deps]]`,与本次改动无关)。
- 源码无指向已删知识库模块的悬空 import;菜单、i18n 已清理。
> 注:worktree 前端 dev 不易直接跑(借用主仓库依赖 + Turbopack 要求根内 node_modules)。如需浏览器实时冒烟,建议在主仓库环境进行。

## 5. 结论
**合入当前 master 后,删除知识库没有破坏其他功能。** 仅有的 2 个分支独有测试失败已确认为删除的预期副作用并完成收尾;现在本分支测试画像与 master 基线一致(仅少了被删的知识库测试)。

## 6. 重要约束
- **该功能暂不合入 master**。所有改动仅保留在 `claude/bold-tu-40b23d`,未 push、未合并。后续是否合入由用户另行决定。
