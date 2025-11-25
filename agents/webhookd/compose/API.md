# Webhookd Compose API

## 概述

通过 webhookd 管理 Docker Compose 服务的 HTTP API。

**基础 URL**: `http://your-server:8080/compose`

## API 列表

### 1. Setup - 配置服务

创建或更新 compose 配置文件并验证。

**端点**: `POST /compose/setup`

**请求体**:
```json
{
  "id": "app-001",
  "compose": "version: \"3.8\"\nservices:\n  web:\n    image: nginx:alpine\n    ports:\n      - \"8080:80\""
}
```

**成功响应**:
```json
{
  "status": "success",
  "id": "app-001",
  "message": "Configuration is valid",
  "file": "/opt/webhookd/compose/app-001/docker-compose.yml"
}
```

**错误响应**:
```json
{
  "status": "error",
  "id": "app-001",
  "message": "Invalid configuration",
  "error": "具体错误信息..."
}
```

---

### 2. Start - 启动服务

启动已配置的 compose 服务。

**端点**: `POST /compose/start`

**请求体**:
```json
{
  "id": "app-001"
}
```

**成功响应**:
```json
{
  "status": "success",
  "id": "app-001",
  "message": "Successfully started"
}
```

**错误响应**:
```json
{
  "status": "error",
  "id": "app-001",
  "message": "Failed to start",
  "error": "端口冲突或其他错误..."
}
```

---

### 3. Stop - 停止服务

停止运行中的 compose 服务。

**端点**: `POST /compose/stop`

**请求体**:
```json
{
  "id": "app-001"
}
```

**成功响应**:
```json
{
  "status": "success",
  "id": "app-001",
  "message": "Successfully stopped"
}
```

---

### 4. Status - 查看状态

查看服务状态，支持单个、多个或全部服务。

#### 4.1 查看单个服务

**端点**: `POST /compose/status`

**请求体**:
```json
{
  "id": "app-001"
}
```

**响应**:
```json
{
  "status": "success",
  "id": "app-001",
  "containers": [
    {
      "Name": "app-001-web-1",
      "State": "running",
      "Status": "Up 5 minutes",
      "Ports": "0.0.0.0:8080->80/tcp"
    }
  ]
}
```

#### 4.2 批量查看多个服务

**请求体**:
```json
{
  "ids": ["app-001", "app-002", "app-003"]
}
```

**响应**:
```json
{
  "status": "success",
  "data": [
    {
      "id": "app-001",
      "status": "success",
      "containers": [...]
    },
    {
      "id": "app-002",
      "status": "success",
      "containers": [...]
    },
    {
      "id": "app-003",
      "status": "error",
      "message": "Compose directory not found"
    }
  ]
}
```

#### 4.3 查看所有服务

**请求体**: 空或不传

**响应**:
```json
{
  "status": "success",
  "data": [
    {
      "id": "app-001",
      "status": "success",
      "containers": [...]
    },
    {
      "id": "app-002",
      "status": "success",
      "containers": [...]
    }
  ]
}
```

---

### 5. Update - 更新并重启

更新配置并重启服务。

**端点**: `POST /compose/update`

**请求体**:
```json
{
  "id": "app-001",
  "compose": "version: \"3.8\"\nservices:\n  web:\n    image: nginx:latest\n    ports:\n      - \"8080:80\""
}
```

**成功响应**:
```json
{
  "status": "success",
  "id": "app-001",
  "message": "Successfully updated and restarted",
  "file": "/opt/webhookd/compose/app-001/docker-compose.yml"
}
```

---

## 使用示例

### 完整工作流

```bash
# 1. 配置服务
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-app",
    "compose": "version: \"3.8\"\nservices:\n  web:\n    image: nginx:alpine\n    ports:\n      - \"8080:80\""
  }' \
  http://localhost:8080/compose/setup

# 2. 启动服务
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"id": "my-app"}' \
  http://localhost:8080/compose/start

# 3. 查看状态
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"id": "my-app"}' \
  http://localhost:8080/compose/status

# 4. 停止服务
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"id": "my-app"}' \
  http://localhost:8080/compose/stop

# 5. 更新配置并重启
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-app",
    "compose": "version: \"3.8\"\nservices:\n  web:\n    image: nginx:latest\n    ports:\n      - \"8080:80\""
  }' \
  http://localhost:8080/compose/update
```

---

## 配置说明

### 环境变量

- `COMPOSE_DIR`: compose 文件存储目录，默认 `/opt/webhookd/compose`

### 目录结构

```
/opt/webhookd/compose/
├── app-001/
│   └── docker-compose.yml
├── app-002/
│   └── docker-compose.yml
└── app-003/
    └── docker-compose.yml
```

---

## 错误码

- `exit 0`: 成功
- `exit 1`: 失败（参数错误、配置无效、启动失败等）

---

## 注意事项

1. **ID 命名规则**: 只允许字母、数字、下划线和连字符
2. **操作顺序**: 必须先 `setup` 再 `start`
3. **端口冲突**: 确保 compose 配置中的端口未被占用
4. **权限要求**: 需要 Docker 操作权限
