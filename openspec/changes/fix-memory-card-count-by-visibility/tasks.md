## 1. 准备测试环境与失败用例(TDD 红)

- [ ] 1.1 在 `server/apps/opspilot/tests/memory/` 下新增 `test_visibility.py`,写入四个 helper 单测场景:团队空间全见、个人空间创建者见、个人空间非创建者不可见、未认证用户空集合
- [ ] 1.2 在 `server/apps/opspilot/tests/memory/` 下新增/扩展集成测试 `test_memory_space_count.py`,断言列表接口 `memory_count` 与详情页接口可见行数相等(团队/个人创建者/个人非创建者三组样本)
- [ ] 1.3 运行 `cd server && make test APP=opspilot TEST=tests/memory/test_visibility.py`,确认新单测**全部 FAIL**(红);确认集成测试 FAIL
- [ ] 1.4 在 worktree 中跑不通单测时,按「worktree vs main repo bash cwd」记忆,在 master 主仓库跑同命令兜底

## 2. 抽 helper 并完成改造(绿)

- [ ] 2.1 在 `server/apps/opspilot/memory/visibility.py`(新文件)实现 `get_visible_memories_qs(user, *, memory_space_id: int) -> QuerySet[Memory]`,逻辑等价于原 `MemoryViewSet.list` 内联过滤
- [ ] 2.2 修改 `server/apps/opspilot/serializers/memory_serializer.py` 的 `MemorySpaceSerializer.get_memory_count`,改为 `get_visible_memories_qs(self.context['request'].user, memory_space_id=instance.id).count()`
- [ ] 2.3 修改 `server/apps/opspilot/viewsets/memory_view.py` 的 `MemoryViewSet.get_queryset`,返回 `get_visible_memories_qs(self.request.user, memory_space_id=<query_params['memory_space']>)`,移除原 list 内联过滤块
- [ ] 2.4 运行 1.3 同命令,确认单测**全部 PASS**(绿);集成测试 PASS

## 3. 质量门禁与回归

- [ ] 3.1 `cd server && make test` 全量回归,确认无新增失败(尤其是 `opspilot` 全部测试)
- [ ] 3.2 `cd server && pre-commit run --all-files`(或等价的 black/isort/flake8)确保格式与导入顺序通过
- [ ] 3.3 在 master 主仓库跑同 pytest 一次(worktree 缺 MINIO env),排除「worktree vs master」因素

## 4. 文档与归档

- [ ] 4.1 跑 `openspec validate fix-memory-card-count-by-visibility --strict`,确认三件套全部通过
- [ ] 4.2 提交变更到 worktree 分支(不推、不 merge master,等用户确认);commit message 中文,前缀遵循「个人 commit 前缀规约」(本次为修复类,用 `fix`)
- [ ] 4.3 用户确认后再同步到 master 并归档:`openspec archive fix-memory-card-count-by-visibility`