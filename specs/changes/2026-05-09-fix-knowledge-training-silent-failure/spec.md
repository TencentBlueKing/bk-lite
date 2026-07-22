# Fix Knowledge Training Silent Failure

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-09-fix-knowledge-training-silent-failure/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Problem

GitHub Issue: https://github.com/TencentBlueKing/bk-lite/issues/2854

**[opspilot] 知识训练失败仍清理任务或写成完成，可能导致状态卡死与结果静默劣化**

在 `server/apps/opspilot/tasks.py` 的 `general_embed_by_document_list` 函数中存在以下问题：

1. **失败时仍然增加 `completed_count`** - 即使文档训练失败，`completed_count` 仍然 +1，导致进度显示不准确
2. **失败时仍然删除任务** - 无论训练是否全部成功，最后都会删除 `KnowledgeTask`，导致失败的任务无法被追踪
3. **异常被静默吞掉** - 异常只是被记录日志，用户无法从 UI 知道训练失败

## Solution (Plan A - Minimal Change)

修改 `general_embed_by_document_list` 函数：

1. 跟踪每个文档的训练成功/失败状态
2. 只有成功时才增加 `completed_count`
3. 失败时确保文档状态被设置为 `ERROR`
4. 只有全部成功时才删除任务，否则保留以便追踪

## Scope

- **Files Changed**: 1 file (`server/apps/opspilot/tasks.py`)
- **No Database Migration**: 不需要修改模型或数据库
- **Backward Compatible**: 完全向后兼容

## Success Criteria

- [ ] 文档训练失败时，`completed_count` 不增加
- [ ] 文档训练失败时，文档状态正确设置为 `ERROR`
- [ ] 有任何文档失败时，`KnowledgeTask` 不被删除
- [ ] 所有文档成功时，行为与之前一致（任务被删除）
- [ ] 现有测试通过

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-09
```

## Work Checklist

## Implementation

- [ ] 1. 修改 `general_embed_by_document_list` 函数
  - 文件: `server/apps/opspilot/tasks.py`
  - 添加 `has_failure` 变量跟踪是否有失败
  - 添加 `success` 变量跟踪当前文档是否成功
  - 检查 `invoke_document_to_es` 后文档状态是否为 ERROR
  - 只有成功时才增加 `completed_count`
  - 异常时确保文档状态设置为 ERROR
  - 只有全部成功时才删除任务

## Verification

- [ ] 2. 运行现有测试确保不破坏功能
  - 命令: `cd server && & "D:\app\venv\bkliteserver\Scripts\python.exe" -m pytest apps/opspilot/tests/ -v`

- [ ] 3. 手动验证（可选）
  - 模拟文档训练失败场景
  - 确认 KnowledgeTask 被保留
  - 确认 completed_count 正确
