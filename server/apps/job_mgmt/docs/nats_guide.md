# NATS 接口调用指南

> 面向第三方 App 开发者，说明如何通过 NATS 调用 BK-Lite 开放接口。

## 1. 安装依赖

```bash
pip install nats-py
```

## 2. 连接配置

| 配置项 | 说明 | 示例 |
|--------|------|------|
| NATS Server | NATS 服务地址 | `nats://localhost:4222` |
| Namespace | Subject 前缀，需与 BK-Lite Server 一致 | `bklite`（默认） |

> BK-Lite Server 的 namespace 由环境变量 `NATS_NAMESPACE` 决定，默认为 `bklite`。
> 调用方的 subject 格式为：`{namespace}.{method_name}`，例如 `bklite.job_script_execute`。

## 3. 调用方式

NATS 接口使用 **Request-Reply** 模式：发送 JSON 请求到指定 subject，等待返回 JSON 响应。

### 基础示例（Python）

```python
import asyncio
import json
import nats


async def call_nats(method: str, data: dict, server: str = "nats://localhost:4222", namespace: str = "bklite", timeout: float = 30):
    """
    调用 BK-Lite NATS 开放接口

    Args:
        method: 接口方法名，如 job_script_execute
        data: 请求参数字典
        server: NATS 服务地址
        namespace: subject 前缀
        timeout: 超时秒数
    
    Returns:
        dict: 响应数据
    """
    nc = await nats.connect(server)
    try:
        subject = f"{namespace}.{method}"
        payload = json.dumps(data).encode()
        response = await nc.request(subject, payload, timeout=timeout)
        return json.loads(response.data.decode())
    finally:
        await nc.close()


# 使用示例
result = asyncio.run(call_nats("job_script_execute", {
    "name": "测试脚本",
    "target_source": "node_mgmt",
    "target_list": [
        {"node_id": "node-abc", "name": "web-01", "ip": "10.0.0.1", "os": "linux", "cloud_region_id": "region-1"}
    ],
    "script_type": "shell",
    "script_content": "echo hello",
    "team": [1],
}))
print(result)
# {"result": true, "data": {"task_id": 123}}
```

### 同步封装（适合非 async 场景）

```python
import asyncio
import json
import nats


class BKLiteNatsClient:
    """BK-Lite NATS 接口同步客户端"""

    def __init__(self, server: str = "nats://localhost:4222", namespace: str = "bklite", timeout: float = 30):
        self.server = server
        self.namespace = namespace
        self.timeout = timeout

    def call(self, method: str, data: dict) -> dict:
        """同步调用 NATS 接口"""
        return asyncio.run(self._request(method, data))

    async def _request(self, method: str, data: dict) -> dict:
        nc = await nats.connect(self.server)
        try:
            subject = f"{self.namespace}.{method}"
            payload = json.dumps(data).encode()
            response = await nc.request(subject, payload, timeout=self.timeout)
            return json.loads(response.data.decode())
        finally:
            await nc.close()


# 使用示例
client = BKLiteNatsClient(server="nats://localhost:4222")

# 查询目标列表
targets = client.call("job_target_list", {"page_size": -1})
print(targets)

# 查询节点列表
nodes = client.call("node_list", {"os": "linux", "page_size": -1})
print(nodes)

# 执行脚本
result = client.call("job_script_execute", {
    "name": "安装补丁",
    "target_source": "node_mgmt",
    "target_list": [
        {"node_id": "node-abc", "name": "web-01", "ip": "10.0.0.1", "os": "linux", "cloud_region_id": "region-1"}
    ],
    "script_type": "shell",
    "script_content": "yum install -y patch-xxx",
    "team": [1],
    "callback_url": "http://my-app:8080/api/callback"
})
task_id = result["data"]["task_id"]

# 查询任务状态
status = client.call("job_status_batch_query", {"task_ids": [task_id]})
print(status)

# 查询任务详情
detail = client.call("job_detail_query", {"task_id": task_id, "team": [1]})
print(detail)
```

## 4. 可用接口列表

| Subject | 说明 | 参数概要 |
|---------|------|----------|
| `bklite.node_list` | 查询节点列表 | `{name, ip, os, page, page_size}` |
| `bklite.job_target_list` | 查询目标列表 | `{name, ip, os_type, page, page_size}` |
| `bklite.job_script_execute` | 脚本执行 | `{name, target_source, target_list, script_type, script_content, team, ...}` |
| `bklite.job_file_distribute` | 文件分发 | `{name, file_keys, target_source, target_list, target_path, team, ...}` |
| `bklite.job_status_batch_query` | 批量查询状态 | `{task_ids}` |
| `bklite.job_detail_query` | 查询作业详情 | `{task_id, team}` |

> 完整参数说明见 [open_api.md](./open_api.md)

## 5. 注意事项

- NATS 接口无需鉴权，信任内网通道。确保 NATS Server 不对外暴露。
- `namespace` 必须与 BK-Lite Server 配置一致（默认 `bklite`），否则消息无法路由。
- 超时建议设为 30-60 秒，脚本执行类接口只是创建任务（快速返回），实际执行异步进行。
- 如果 NATS Server 配置了认证（用户名/密码/token），连接时需传入对应参数：
  ```python
  nc = await nats.connect("nats://user:password@localhost:4222")
  ```
- 文件上传/删除使用 REST 接口（非 NATS），见 [open_api.md](./open_api.md) 中对应章节。
