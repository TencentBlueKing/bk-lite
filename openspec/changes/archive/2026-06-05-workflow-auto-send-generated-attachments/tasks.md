## 1. Backend attachment automation

- [x] 1.1 Update Agent 节点执行逻辑，根据所选 skill 是否包含 `attachment_file` 工具自动启用附件生成能力，并移除对手工 `attachmentId` 配置的依赖。
- [x] 1.2 调整附件资产登记逻辑，为同一节点在一次 execution 内生成的多个附件分配系统化且唯一的 `attachment_id`，同时保留 `source_node_id` 和下载链接绑定。
- [x] 1.3 更新通知节点附件构造逻辑，邮件发送时自动收集当前 `execution_id` 下全部附件资产并复用现有 MinIO 文件读取链路发送。

## 2. Frontend workflow configuration cleanup

- [x] 2.1 移除 Agent 节点配置面板中的附件开关、附件 ID、附件名称等手工字段，并保持其余智能体配置正常保存。
- [x] 2.2 移除通知节点中的附件选择配置，改为仅展示“邮件会自动附带本次运行生成的全部附件”的语义。
- [x] 2.3 清理 chatflow 默认配置、类型定义、节点摘要和中英文文案中的旧附件字段，避免继续写入无效配置。

## 3. Validation

- [x] 3.1 更新并补齐现有 workflow 附件相关测试，覆盖 skill 工具能力识别、自动附件收集和多附件 asset 生成。
- [x] 3.2 运行 server 侧相关 pytest 用例以及 web 的 type-check，确认自动附件发送链路可用且无类型错误。
