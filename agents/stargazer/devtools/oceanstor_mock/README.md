# OceanStor DeviceManager mock

**TEST-ONLY / 本地联调**，不进默认生产采集路径，不改任务树默认值，不碰 FDB / `interface_connect_*` / mapping。
语义对齐现有 `oceanstor_https` 采集器：`POST /deviceManager/rest/xxxxx/sessions`（`scope=0`）拿 `iBaseToken` + `deviceid`，再 `GET /{deviceid}/{resource}`。

产品锁定夹具：以太口主键 `MACADDR`（另有一条仅 `MACADDRESS` 别名）；FC 口主键 `WWPN`（另有一条仅 `WWN` 别名）。无 MAC / 无 WWPN 原样返回，采集映射跳过，**不编造**身份。

## 覆盖端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/deviceManager/rest/xxxxx/sessions` | 登录，返回 `iBaseToken` + `deviceid` |
| `DELETE` | `/deviceManager/rest/{deviceid}/sessions` | 登出 |
| `GET` | `/deviceManager/rest/{deviceid}/system` | 型号 / 微码（`PRODUCTMODESTRING` / `PRODUCTVERSION`） |
| `GET` | `/deviceManager/rest/{deviceid}/storagepool` | 存储池，支持 `range=[start-end]` |
| `GET` | `/deviceManager/rest/{deviceid}/disk` | 磁盘 |
| `GET` | `/deviceManager/rest/{deviceid}/lun` | 卷 |
| `GET` | `/deviceManager/rest/{deviceid}/eth_port` | `MACADDR` 一条、仅 `MACADDRESS` 一条、空 MAC 一条（空身份跳过） |
| `GET` | `/deviceManager/rest/{deviceid}/fc_port` | `WWPN` 一条、仅 `WWN` 一条、`WWPN=--` 一条（空身份跳过） |

后续 GET 必须带登录下发的 `iBaseToken` 头。

## 启动

在 `agents/stargazer` 目录：

```bash
# HTTP，默认 127.0.0.1:18088（避开真机 8088）
uv run python -m devtools.oceanstor_mock.server

# 自签 HTTPS（采集任务把 verify_tls 设为 false）
uv run python -m devtools.oceanstor_mock.server --tls --port 8088
```

默认账号：`admin` / `Admin@storage`，`deviceid=2102355TJUN0S1100017`。

## 把采集任务指过来

CMDB 存储采集对象协议是 `oceanstor_https`（默认 8088）。对 mock：

| 凭据字段 | HTTP mock | HTTPS mock |
|---|---|---|
| host / 实例 IP | `127.0.0.1` | `127.0.0.1` |
| port | `18088` | `8088` |
| scheme | `http` | `https` |
| username | `admin` | `admin` |
| password | `Admin@storage` | `Admin@storage` |
| verify_tls | `false` | `false`（自签证书） |

Stargazer 插件直接调：

```python
OceanStorManager({
    "host": "127.0.0.1",
    "port": 18088,
    "scheme": "http",
    "username": "admin",
    "password": "Admin@storage",
    "verify_tls": False,
})
```

curl 登录示例：

```bash
curl -sS -X POST 'http://127.0.0.1:18088/deviceManager/rest/xxxxx/sessions' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin@storage","scope":"0"}'
```

## 冒烟

```bash
cd agents/stargazer
uv run python -m devtools.oceanstor_mock.smoke
uv run pytest -q -o addopts='' tests/test_oceanstor_mock_smoke.py
```

CMDB 映射（空 MAC/WWPN 跳过 + `storage contains` 口）用同一套夹具：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/cmdb/tests/test_oceanstor_mock_mapping.py --no-cov
```

采集侧原始回包保留无 MAC / 无 WWPN 的口；CMDB `format_metrics` 按身份跳过，不把 NAME/LOCATION 当成 MAC/WWPN。有身份的口写 `storage_contains_storage_eth_port` / `storage_contains_storage_fc_port`。
