# CMDB OpenAPI Python 调用指南

本文用“查询实例”和“创建实例”演示如何从 Python 调用 CMDB OpenAPI。完整接口字段见 [CMDB OpenAPI 接口说明](open_api.md)。

## 1. 调用前准备

准备以下信息：

- BK-Lite 根地址，例如 `https://bk-lite.example.com`。
- 一个有效的 API Token。请登录 BK-Lite 产品页面，在“系统管理 → 平台设置 → 密钥”中申请。产品页面申请到的 API Token 即本文和请求头中使用的 API Secret。
- API Token 必须只绑定一个团队，并关联到有相应 CMDB 权限的用户。
- 要操作的模型 ID，例如 `host`。
- 创建实例时，需要先通过属性接口确认字段 ID、类型、必填性和可编辑性。

安装 Python 依赖：

```bash
python -m pip install 'requests>=2.32.4'
```

不要把 API Secret 写进代码或提交到 Git。示例统一从环境变量读取：

```bash
export CMDB_API_SECRET='<你的 API Secret>'
```

## 2. 最小调用代码

### 2.1 查询实例

```python
import json
import os

import requests

base_url = "https://bk-lite.example.com"
model_id = "host"
url = f"{base_url}/api/v1/cmdb/api/open/models/{model_id}/instances"

filters = [
    {"field": "inst_name", "type": "str*", "value": "web"},
]
response = requests.get(
    url,
    headers={
        "Api-Authorization": os.environ["CMDB_API_SECRET"],
        "Accept": "application/json",
    },
    params={
        "page": 1,
        "page_size": 20,
        "order": "-inst_id",
        "filters": json.dumps(filters, ensure_ascii=False),
    },
    timeout=10,
)

payload = response.json()
if not payload.get("result"):
    raise RuntimeError(
        f"调用失败：HTTP {response.status_code}，"
        f"{payload.get('code')}，{payload.get('message')}"
    )
response.raise_for_status()

data = payload["data"]
print(f"共 {data['count']} 条")
for instance in data["items"]:
    print(instance["inst_id"], instance.get("inst_name"))
```

关键点：

- `filters` 在 URL Query 中传递，但它的值本身是 JSON 数组字符串。
- `requests` 的 `params` 会负责 URL 编码，不要手工拼接过滤条件。
- 必须同时检查 HTTP 状态和响应体中的 `result`。
- 调用一定要设置超时。

### 2.2 创建实例

```python
import os

import requests

base_url = "https://bk-lite.example.com"
model_id = "host"
url = f"{base_url}/api/v1/cmdb/api/open/models/{model_id}/instances"

response = requests.post(
    url,
    headers={
        "Api-Authorization": os.environ["CMDB_API_SECRET"],
        "Accept": "application/json",
    },
    json={
        "inst_name": "host-01",
        "ip": "10.0.0.1",
    },
    timeout=10,
)

payload = response.json()
if not payload.get("result"):
    raise RuntimeError(
        f"创建失败：HTTP {response.status_code}，"
        f"{payload.get('code')}，{payload.get('message')}，"
        f"上下文={payload.get('data')}"
    )
response.raise_for_status()

instance = payload["data"]
print(f"创建成功，实例 ID={instance['inst_id']}")
```

创建时不要提交 `organization`。服务端会使用 API Secret 绑定的唯一团队强制设置实例所属团队。

## 3. 使用仓库内可运行示例

仓库提供了可复用客户端：

```text
server/apps/cmdb/examples/open_api_client.py
```

它实现了：

- `CMDBOpenAPIClient.list_instances()`：查询实例。
- `CMDBOpenAPIClient.create_instance()`：创建实例。
- 统一请求头、10 秒默认超时、稳定错误提示和模型 ID URL 编码。

在 `server` 目录运行查询：

```bash
export CMDB_API_SECRET='<你的 API Secret>'
uv run python -m apps.cmdb.examples.open_api_client \
  --base-url 'http://127.0.0.1:8011' \
  --model-id host \
  --action list \
  --filters '[{"field":"inst_name","type":"str*","value":"web"}]'
```

运行创建：

```bash
export CMDB_API_SECRET='<你的 API Secret>'
uv run python -m apps.cmdb.examples.open_api_client \
  --base-url 'http://127.0.0.1:8011' \
  --model-id host \
  --action create \
  --payload '{"inst_name":"host-01","ip":"10.0.0.1"}'
```

也可以在业务代码中导入：

```python
import os

from apps.cmdb.examples.open_api_client import CMDBOpenAPIClient

client = CMDBOpenAPIClient(
    "https://bk-lite.example.com",
    os.environ["CMDB_API_SECRET"],
)

instances = client.list_instances(
    "host",
    filters=[{"field": "inst_name", "type": "str*", "value": "web"}],
)
created = client.create_instance(
    "host",
    {"inst_name": "host-02", "ip": "10.0.0.2"},
)
```

## 4. 实际测试

客户端示例配有真实 HTTP 调用测试。测试会在本机随机端口启动一个临时 HTTP 服务，然后让 `requests` 通过 TCP 发出 GET 和 POST 请求，并验证：

- URL 路径及 Query 编码正确。
- `Api-Authorization` 请求头正确。
- 创建实例发送的是 JSON 请求体。
- 客户端能解析统一响应结构并返回 `data`。

运行命令：

```bash
cd server
uv run pytest apps/cmdb/tests/test_open_api_client_example.py -q --no-cov
```

预期结果：

```text
2 passed
```

服务端契约测试可运行：

```bash
cd server
uv run pytest \
  apps/cmdb/tests/test_open_api_model_views.py \
  apps/cmdb/tests/test_open_api_instance_views.py \
  apps/cmdb/tests/test_open_api_batch_views.py \
  apps/cmdb/tests/test_open_api_association_views.py \
  -q --no-cov
```

这些测试覆盖认证错误结构、模型查询、实例 CRUD、批量操作、关联操作、团队隔离和主要错误码。

## 5. 生产调用建议

- API Secret 通过密钥管理系统或部署环境注入，不要写入日志。
- 为连接超时和读取超时设置明确上限；需要更细控制时可传 `(3.05, 10)` 给 `requests`。
- 只对网络超时和 5xx 做有限次数重试；创建、更新、删除重试前必须确认业务幂等性。
- 记录 `code`、HTTP 状态码和请求标识，不要记录 Secret。
- 批量操作最多 100 条；更大数据集需要调用方分批，并保存每批结果。
- 写入前先查 `/models/{model_id}/attributes`，不要硬编码未经确认的字段类型。
