## 1. 决策规则数据模型与迁移

- [x] 1.1 在 `server/apps/opspilot/tests/wiki/test_decision_replay.py` 增加失败测试：`WikiDecisionRule` 的 `knowledge_base`、`decision_type`、`decision_key`、快照、动作、结果、状态和回放计数字段可持久化。
- [x] 1.2 在同一测试文件增加失败测试：同一知识库、决策类型和 `decision_key` 不能保存两条有效规则，不同知识库或不同类型可以保存相同摘要。
- [x] 1.3 在 `server/apps/opspilot/models/wiki_mgmt.py` 新增 `WikiDecisionRule`，并给决策型 `CheckItem` 增加可索引的 `decision_key` 与冻结的 `decision_context` 字段。
- [x] 1.4 生成并检查 `server/apps/opspilot/migrations/0064_*.py`，迁移使用普通字段唯一约束和数据库无关索引，不回填历史决策。
- [x] 1.5 运行 `cd server; uv run pytest apps/opspilot/tests/wiki/test_decision_replay.py -q`，确认模型与迁移测试通过。

## 2. 稳定签名与规则服务

- [x] 2.1 在 `test_decision_replay.py` 增加失败测试：一对一来源、多来源集合、来源排序、重复来源、同资料新版本 ID、不同资料 ID、角色反转和 Schema 指纹生成确定且可区分的签名。
- [x] 2.2 在 `server/apps/opspilot/services/wiki/decision_service.py` 实现来源快照规范化、知识主题 key、页面身份 key、Schema 指纹和 SHA-256 决策签名；主签名使用 `material_id + content_hash`，版本 ID 与正文 hash 只用于审计/校验。
- [x] 2.3 增加失败测试：缺少来源 ID/content hash、无稳定知识主题、人工结果正文已变化、来源集合增加/减少时规则不可回放。
- [x] 2.4 实现规则查询、结果前置条件校验、`replayed`/`pending`/`unchanged` 结果、规则 upsert、撤销和回放计数更新。
- [x] 2.5 增加失败测试：物理删除资料或页面、恢复合并归档页面、页面身份变化时相关规则被撤销；撤销不回滚当前知识。
- [x] 2.6 实现 `revoke_rules_for_materials`、`revoke_rules_for_pages`、`revoke_rules_for_identity_change`，并为规则快照保留可审计来源而不复制全文到通用日志。

## 3. 知识冲突审批与证据一致性

- [x] 3.1 在 `server/apps/opspilot/tests/wiki/test_checks.py` 增加失败测试：知识冲突只接受 `keep_current`、`use_new`、`edit_accept`，错误动作和空编辑正文被拒绝且不改变页面。
- [x] 3.2 在 `server/apps/opspilot/services/wiki/check_service.py` 重构候选创建与决策处理：冻结完整来源上下文，统一执行三种知识结果，并在同一事务中写入 `WikiDecisionRule`。
- [x] 3.3 增加失败测试：保留当前知识不补入被拒绝资料；使用新知识和编辑后采用都补齐资料/资料版本 `PageEvidence`，旧页面版本可恢复。
- [x] 3.4 修复 `accept_candidate`、编辑后采用和拒绝流程的当前版本竞态：提交时锁定页面并重新校验候选创建时的当前版本，过期决策不得覆盖更新后的页面。
- [x] 3.5 在 `server/apps/opspilot/viewsets/wiki_check_view.py` 增加语义化 `POST /check_item/{id}/decide/` 与规则撤销接口，按 `check_type` 校验允许动作；移除生产 Web 对通用 accept/reject/batch 动作的依赖。
- [x] 3.6 在 `server/apps/opspilot/serializers/wiki_serializers.py` 暴露决策类型、冻结来源、动作、规则 ID、回放次数和未回放原因；补充接口契约测试与无权限撤销测试。

## 4. 普通构建、资料更新和全库重建接入

- [x] 4.1 在 `server/apps/opspilot/tests/wiki/test_build.py` 增加失败测试：同一资料内容再次构建、相同冲突角色反转、候选正文与当前正文相同以及多来源集合命中时不重复创建审批。
- [x] 4.2 修改 `server/apps/opspilot/services/wiki/build_service.py`：在 `_create_review_candidate` 前调用统一决策服务，回放时保持已审批结果，未命中时创建带来源快照的候选，并在 `BuildRecord.inputs.source_trace.page_actions` 写入 `decision_reused`。
- [x] 4.3 在 `server/apps/opspilot/tests/wiki/test_update.py` 增加失败测试：资料重新摄取相同 hash 命中旧规则，hash 变化或来源集合变化重新创建知识冲突；`apply_material_update` 必须携带资料上下文。
- [x] 4.4 修改 `server/apps/opspilot/services/wiki/update_service.py`，让资料更新复用普通构建的决策编排、证据补齐和规则写入，不再为同一版本重复生成候选。
- [x] 4.5 在 `server/apps/opspilot/tests/wiki/test_rebuild.py` 增加失败测试：整体重建同 Schema 命中历史决策不创建审批，Schema 变化重新决策，重建确定性维护不创建 `schema_changed` 审批。
- [x] 4.6 修改 `server/apps/opspilot/services/wiki/rebuild_service.py`，替换无候选上下文的 `ensure_check` 分支，使用统一冲突处理器并记录真实资料/正文快照。
- [x] 4.7 增加异步任务回归测试，验证 `wiki_build_material_task`、`wiki_rebuild_kb_task` 和 BuildRecord retry 与同步入口得到相同回放结果。
- [x] 4.8 补齐 AI 资料事实冲突检测：Stage2 返回经当前知识库校验的 `existing_page_id`，新旧正文仅在明确矛盾时进入现有知识冲突审批，标题漂移回归用例覆盖报销 A/B 场景。

## 5. 页面身份合并与生命周期

- [x] 5.1 在 `test_decision_replay.py` 和 `server/apps/opspilot/tests/wiki/test_checks.py` 增加失败测试：保持独立、确认合并、扫描顺序反转、重建后页面 ID 变化和来源资料变化的行为符合页面身份规则。
- [x] 5.2 在 `server/apps/opspilot/services/wiki/check_service.py` 抽出稳定页面身份签名和可复用的页面合并核心；`merge_duplicate_check` 记录目标身份与规则结果，不依赖 related 页面数组位置。
- [x] 5.3 修改 `scan_health`/`ensure_check`，先查询 `page_identity` 规则；命中 `keep_separate` 时跳过检查，命中 `merge` 时自动合并到记录的目标身份。
- [x] 5.4 在 `server/apps/opspilot/tests/wiki/test_page_lifecycle_incremental.py` 增加失败测试：恢复合并归档页面先撤销合并规则，页面重命名/类型变化和物理删除撤销相关身份规则。
- [x] 5.5 修改 `server/apps/opspilot/viewsets/wiki_page_view.py` 与 `page_service.py`，把恢复、编辑身份、物理删除接入规则撤销；保持当前页面内容，不隐式拆分已完成合并。

## 6. 删除与确定性维护自动化

- [x] 6.1 在资料删除测试中增加失败测试：删除前返回唯一来源/共享来源影响预览，取消删除不改变数据，确认删除不创建 `source_invalid` 待决策。
- [x] 6.2 修改 `server/apps/opspilot/services/wiki/update_service.py` 的删除流程，物理删除后自动清理证据、页面状态、关系、图谱、索引和相关决策规则；唯一来源与共享来源分别验证。
- [x] 6.3 在知识页面删除测试中验证物理删除自动清理关系、索引和 page identity 规则，且不增加待决策数量。
- [x] 6.4 调整 `sweep_service.py` 与构建计数，使确定性失效、结构维护和技术失败只进入构建/维护追踪，不进入用户待决策列表。
- [x] 6.5 增加级联维护失败与重试测试：核心知识结果保持已提交，失败阶段可重试，不创建新的用户决策。

## 7. 生产 API、决策中心与 Storybook

- [x] 7.1 在 `web/src/app/opspilot/types/wiki.ts` 增加决策动作、来源快照、规则回放和撤销类型；在 `web/src/app/opspilot/api/wiki.ts` 实现 `decide`、撤销和处理记录查询。
- [x] 7.2 重构 `web/src/app/opspilot/components/wiki/CheckTab.tsx` 为生产决策中心：待处理仅显示知识冲突/页面合并，使用当前知识/新知识双侧布局和语义化动作。
- [x] 7.3 实现知识冲突的“保留当前知识”“使用新知识”“编辑后采用”交互，包括正文编辑、过期决策提示、提交中状态和成功后刷新。
- [x] 7.4 实现页面合并的“保持独立”“确认合并”交互，统一左右对比图标和双侧卡片风格；移除“更多处理”、通用忽略和无上下文批量操作。
- [x] 7.5 将 `web/src/stories/wiki-decision-center.stories.tsx` 改为复用生产决策中心组件，保留知识冲突、页面合并、自动回放和失效状态 stories。
- [x] 7.6 更新 `web/src/app/opspilot/locales/zh.json`、`en.json` 及 `web/scripts/wiki-check-review-i18n-test.ts`，覆盖语义化动作、回放、撤销、自动维护和失败提示。
- [x] 7.7 更新已处理记录/变更记录展示：显示决策结果、规则状态、回放次数、失效原因和可撤销入口，不展示资料全文。

## 8. 并发、回归与质量门禁

- [x] 8.1 增加并发测试：相同签名的两个构建最多创建一条 open 决策和一条候选，两个回放任务不重复创建页面版本、证据或合并结果。
- [x] 8.2 增加回归测试：旧 `CheckItem` 无完整上下文不被回填，物理删除/归档恢复/资料 hash 回退/新资料 ID 均符合失效规则。
- [x] 8.3 运行 `cd server; uv run pytest apps/opspilot/tests/wiki/test_decision_replay.py apps/opspilot/tests/wiki/test_checks.py apps/opspilot/tests/wiki/test_build.py apps/opspilot/tests/wiki/test_update.py apps/opspilot/tests/wiki/test_rebuild.py apps/opspilot/tests/wiki/test_page_lifecycle_incremental.py -q`。
- [ ] 8.4 运行 `cd server; make test`，确认迁移检查、后端回归和覆盖率门禁通过。
- [ ] 8.5 运行 `cd web; pnpm lint; pnpm type-check; pnpm build-storybook`，确认生产决策中心与 Storybook 视觉伴随通过。
- [x] 8.6 运行 `openspec validate streamline-wiki-knowledge-decisions --strict --no-interactive`，再用 `openspec status --change streamline-wiki-knowledge-decisions` 确认四个 artifact 完成。

## 当前验证记录（2026-07-15）

| 范围 | 状态 | 证据 |
|------|------|------|
| 1-7 实现任务 | ✅ 完成 | 对应代码与测试均已落盘，并纳入受影响后端测试和前端定向检查。 |
| 8.1-8.3 并发与回归 | ✅ 完成 | 受影响后端 20 个测试文件共 356 passed，覆盖终审补充的历史上下文、重建快照、页面身份清扫与锁顺序回归。 |
| 8.4 `make test` | ⏳ 未完成 | 尚未运行 `make test`，不以局部测试替代全量后端门禁。 |
| 8.5 Web/Storybook | 🟡 部分完成 | `test:wiki-decision-center`、QA save-answer 脚本、定向 TypeScript 与 ESLint、fresh Storybook build 已通过；尚未运行全 Web 工作区 `pnpm lint` 与 `pnpm type-check`。 |
| 8.6 OpenSpec | ✅ 完成 | strict validate 通过，status 显示 `4/4 artifacts complete`。 |

补充静态检查：变更 Python 文件 Ruff 通过，`compileall` 通过，`git diff --check` 通过；`makemigrations --check --dry-run` 返回 `No changes detected`，同时出现本地非测试数据库连接 warning。
