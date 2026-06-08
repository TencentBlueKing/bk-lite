## 1. Model 层

- [x] 1.1 在 `server/apps/opspilot/models/model_provider_mgmt.py` 的 LLMSkill 模型中新增 `skill_params = models.JSONField(default=list, verbose_name="技能参数")`
- [x] 1.2 生成并执行 Django migration：`python manage.py makemigrations opspilot && python manage.py migrate`

## 2. 工具函数

- [x] 2.1 新建 `server/apps/opspilot/utils/prompt_utils.py`，实现 `resolve_skill_params(skill_prompt, skill_params)` 函数：深拷贝 skill_params → 解密 password 类型 → `{{key}}` 替换为真实值 → 返回替换后的 prompt

## 3. Serializer 层

- [x] 3.1 在 `server/apps/opspilot/serializers/llm_serializer.py` 的 LLMSerializer 中新增 `skill_params = serializers.SerializerMethodField()`
- [x] 3.2 实现 `get_skill_params()` 方法：遍历参数列表，`type=password` 的 value 替换为 `"******"` 后返回

## 4. View 层 — 创建

- [x] 4.1 在 `server/apps/opspilot/viewsets/llm_view.py` 的 `create()` 方法中，保存前遍历 `params.get("skill_params", [])`，对 `type=password` 的条目调用 `EncryptMixin.encrypt_field("value", item)`

## 5. View 层 — 更新

- [x] 5.1 在 `llm_view.py` 的 `update()` 方法中，处理 `skill_params` 更新逻辑：遍历新参数列表，`type=password` 且 `value=="******"` 时从 `instance.skill_params` 中找同 key 的旧加密值保留；否则加密新值

## 6. 执行路径 — 直接执行

- [x] 6.1 在 `server/apps/opspilot/services/chat_service.py` 中，构建 `chat_kwargs` 之前（约第 154 行），从 DB 加载 skill 的 `skill_params`（不信任前端传入值），调用 `resolve_skill_params()` 替换 prompt 中的参数
- [x] 6.2 在 `llm_view.py` 的 `execute()` 方法中，根据 skill ID 从 DB 读取 `skill_params` 传入 `chat_service`，确保使用加密存储的真实值而非前端掩码值

## 7. 执行路径 — 工作流 AgentNode

- [x] 7.1 在 `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` 的 `_build_llm_params()` 中，读取 `skill.skill_params`，调用 `resolve_skill_params()` 处理 `skill.skill_prompt` 后再赋值到返回字典

## 8. 前端 — Skill 设置页 Prompt 参数区域

- [x] 8.1 在 `web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx` 的 Prompt TextArea 下方，新增 "Prompt 参数" 区域，使用 Ant Design `Form.List name="skill_params"` 渲染动态参数行
- [x] 8.2 每行包含：参数名（Input）、值（根据 type 切换：text→Input，password→EditablePasswordField）、类型（Select: text/password）、删除按钮
- [x] 8.3 添加 "添加参数" 按钮，点击追加空行 `{key: "", value: "", type: "text"}`
- [x] 8.4 保存时将 `skill_params` 数组一并提交到 PUT 请求 payload 中

## 9. 前端 — 测试执行传参

- [x] 9.1 在 `handleSendMessage` 函数中，将当前表单的 `skill_params` 传入执行请求 payload（后端将从 DB 读取真实加密值，前端传入仅用于标识 skill）

## 10. 前端 — 国际化

- [x] 10.1 在 opspilot 的 locale 文件中添加新增 UI 文案的 i18n key（中/英文）："Prompt 参数"、"参数名"、"值"、"类型"、"添加参数" 等

## 11. 前端 — 数据回填

- [x] 11.1 页面加载时，从 GET 接口返回的 `skill_params` 初始化 Form 表单（password 值为 "******"，显示为密码输入框）
- [x] 11.2 编辑保存时，未修改的 password 字段保持 "******" 原样回传，后端保留旧加密值

## 12. 验证

- [x] 12.1 运行 `cd server && make test` 确保后端测试通过
- [x] 12.2 运行 `cd web && pnpm lint && pnpm type-check` 确保前端检查通过
- [x] 12.3 手动验证：创建带 password 参数的 LLMSkill，确认 API 返回掩码值
- [x] 12.4 手动验证：执行带参数的 skill，确认 prompt 中 `{{key}}` 被正确替换
- [x] 12.5 手动验证：在设置页右侧聊天面板测试执行，确认 password 参数能正确替换（非 "******"）
