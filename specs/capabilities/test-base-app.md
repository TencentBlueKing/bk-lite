## ADDED Requirements

### Requirement: User 模型 Factory
系统 SHALL 提供 `UserFactory`，基于 factory-boy 创建 `apps.base.models.User` 测试实例。

#### Scenario: 默认 User 创建
- **WHEN** 调用 `UserFactory()`
- **THEN** SHALL 创建一个 User，包含随机 username、默认 domain="domain.com"、空 group_list 和 roles

#### Scenario: 自定义字段
- **WHEN** 调用 `UserFactory(locale="en", roles=["admin"])`
- **THEN** SHALL 创建 User 并覆盖指定字段值

### Requirement: UserAPISecret 模型 Factory
系统 SHALL 提供 `UserAPISecretFactory`，基于 factory-boy 创建 `UserAPISecret` 测试实例。

#### Scenario: 默认 UserAPISecret 创建
- **WHEN** 调用 `UserAPISecretFactory()`
- **THEN** SHALL 创建一个 UserAPISecret，包含随机 username、有效 api_secret（64字符 hex）、team=0

#### Scenario: 关联用户创建
- **WHEN** 调用 `UserAPISecretFactory(username="alice", domain="test.com", team=1)`
- **THEN** SHALL 创建对应字段值的 UserAPISecret

### Requirement: generate_api_secret 单元测试
UserAPISecret.generate_api_secret() 的行为 SHALL 被完整测试。

#### Scenario: 返回格式
- **WHEN** 调用 `UserAPISecret.generate_api_secret()`
- **THEN** SHALL 返回一个 64 字符的十六进制字符串

#### Scenario: 唯一性
- **WHEN** 连续调用两次 `UserAPISecret.generate_api_secret()`
- **THEN** 两次返回值 SHALL 不同

### Requirement: User 模型约束测试

#### Scenario: unique_together 约束
- **WHEN** 创建两个 username 和 domain 都相同的 User
- **THEN** 第二次创建 SHALL 引发 IntegrityError

### Requirement: UserAPISecret 模型约束测试

#### Scenario: unique_together 约束
- **WHEN** 创建两个 username、domain、team 都相同的 UserAPISecret
- **THEN** 第二次创建 SHALL 引发 IntegrityError

### Requirement: UserAPISecretSerializer 序列化测试

#### Scenario: team_name 解析
- **WHEN** 序列化一个 team=1 的 UserAPISecret，且 request.user.group_list 包含 `{"id": 1, "name": "Team A"}`
- **THEN** 序列化输出 SHALL 包含 `team_name: "Team A"`

#### Scenario: team_name 找不到匹配
- **WHEN** 序列化一个 team=999 的 UserAPISecret，且 group_list 中无对应 id
- **THEN** team_name SHALL 返回 team 的数值（999）

### Requirement: _parse_current_team 工具函数测试

#### Scenario: 有效整数 cookie
- **WHEN** request.COOKIES["current_team"] = "5"
- **THEN** SHALL 返回 `(5, None)`

#### Scenario: 无效 cookie 值
- **WHEN** request.COOKIES["current_team"] = "abc"
- **THEN** SHALL 返回 `(None, JsonResponse)` 且 JsonResponse 状态码为 400

#### Scenario: 缺失 cookie
- **WHEN** request.COOKIES 中无 current_team
- **THEN** SHALL 返回 `(0, None)`（默认值为 "0"）

### Requirement: API Secret 列表接口测试

#### Scenario: 认证用户查看自己的 secrets
- **WHEN** 用户 "alice"（team=1）发起 GET /user_api_secret/
- **THEN** SHALL 仅返回属于 "alice" 且 team=1 的 secrets

#### Scenario: 不同用户数据隔离
- **WHEN** "alice" 和 "bob" 各有 secrets，"alice" 发起 GET 请求
- **THEN** SHALL 不包含 "bob" 的 secrets

#### Scenario: 未认证用户
- **WHEN** 未认证用户发起 GET /user_api_secret/
- **THEN** SHALL 返回 401 或 403

### Requirement: API Secret 创建接口测试

#### Scenario: 成功创建
- **WHEN** 认证用户 POST /user_api_secret/，且该用户在当前 team 下没有 secret
- **THEN** SHALL 返回 201，响应包含生成的 api_secret

#### Scenario: 重复创建被拒绝
- **WHEN** 用户已有 secret，再次 POST 创建
- **THEN** SHALL 返回 `result: false` 和"已存在"提示

#### Scenario: 无效 current_team cookie
- **WHEN** POST 请求的 current_team cookie 为 "abc"
- **THEN** SHALL 返回 400 错误

### Requirement: API Secret 删除接口测试

#### Scenario: 成功删除
- **WHEN** 认证用户 DELETE /user_api_secret/{id}/
- **THEN** SHALL 返回 204，数据库中该记录被删除

### Requirement: API Secret 更新被禁止

#### Scenario: PUT 请求被拒绝
- **WHEN** 发起 PUT /user_api_secret/{id}/
- **THEN** SHALL 返回 `result: false` 和"不支持修改"消息

### Requirement: generate_api_secret action 测试

#### Scenario: 生成新密钥
- **WHEN** POST /user_api_secret/generate_api_secret/
- **THEN** SHALL 返回 `result: true` 和一个 64 字符 hex 的 api_secret

### Requirement: BDD 场景 — API Secret 管理全流程

#### Scenario: 完整生命周期
- **WHEN** 用户创建 API Secret，然后查看列表，最后删除
- **THEN** 创建返回 201，列表包含该 secret，删除返回 204，再次列表为空

#### Scenario: 多团队隔离
- **WHEN** 同一用户在 team=1 和 team=2 分别创建 secret
- **THEN** 切换 current_team cookie 后，列表 SHALL 只显示对应 team 的 secret
