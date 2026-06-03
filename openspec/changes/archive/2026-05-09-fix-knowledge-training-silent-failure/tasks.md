# Tasks

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
