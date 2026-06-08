## ADDED Requirements

### Requirement: 引擎列表 API
系统 SHALL 提供 API 端点返回所有可用的记忆引擎列表。

#### Scenario: 获取引擎列表
- **WHEN** 发送 `GET /api/opspilot/memory_engines/`
- **THEN** 返回 200，body 为引擎列表：
  ```json
  {
    "result": true,
    "data": [
      {"type": "local", "name": "本地存储", "description": "..."},
      {"type": "mem0", "name": "Mem0", "description": "..."},
      {"type": "zep", "name": "Zep", "description": "..."},
      {"type": "custom", "name": "自定义 API", "description": "..."}
    ]
  }
  ```

### Requirement: 引擎 Schema API
系统 SHALL 提供 API 端点返回指定引擎的配置参数定义。

#### Scenario: 获取引擎 Schema
- **WHEN** 发送 `GET /api/opspilot/memory_engines/mem0/schema/`
- **THEN** 返回 200，body 包含引擎信息和字段定义：
  ```json
  {
    "result": true,
    "data": {
      "type": "mem0",
      "name": "Mem0",
      "description": "...",
      "fields": [
        {"name": "api_key", "label": "API Key", "type": "password", "required": true, "encrypted": true},
        {"name": "base_url", "label": "API 地址", "type": "text", "required": false, "default": "https://api.mem0.ai"}
      ]
    }
  }
  ```

#### Scenario: 获取不存在的引擎 Schema
- **WHEN** 发送 `GET /api/opspilot/memory_engines/unknown/schema/`
- **THEN** 返回 400，body 包含错误信息

### Requirement: 引擎连接测试 API
系统 SHALL 提供 API 端点测试引擎配置是否有效。

#### Scenario: 测试连接成功
- **WHEN** 发送 `POST /api/opspilot/memory_engines/mem0/test/`，body 包含有效配置
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": true, "message": "连接成功"}}`

#### Scenario: 测试连接失败
- **WHEN** 发送 `POST /api/opspilot/memory_engines/mem0/test/`，body 包含无效配置
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": false, "message": "认证失败: Invalid API key"}}`

#### Scenario: 测试本地引擎
- **WHEN** 发送 `POST /api/opspilot/memory_engines/local/test/`
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": true, "message": "本地存储无需测试"}}`

### Requirement: API 权限控制
引擎 API SHALL 要求用户登录认证。

#### Scenario: 未认证访问
- **WHEN** 未携带认证 token 访问引擎 API
- **THEN** 返回 401 Unauthorized

#### Scenario: 认证用户访问
- **WHEN** 携带有效认证 token 访问引擎 API
- **THEN** 正常返回数据
