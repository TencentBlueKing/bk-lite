# Dell Unity Unisphere REST mock

**TEST-ONLY / 本地联调**，不进默认生产采集路径，不改任务树默认值，不碰 FDB / `interface_connect_*` / mapping / canvas / storops。
语义对齐 `dell_unity_https`：HTTP Basic，`base_path=/api`，请求头 `X-EMC-REST-CLIENT: true`。
无 MAC / 无 WWPN 原样返回，采集映射跳过，**不编造**身份。

字段按官方 Unisphere REST 属性校准：`system.serialNumber` / `model` / `softwareVersion`，
`lun.wwn` + `pool.name`，`ethernetPort.macAddress`，`fcPort.wwn`（WWPN）。
`health.value=5` 为官方 `HealthEnum.OK`。`diskTechnology` / `pool.type` 保持数字原文，不臆造 SSD/RAID 名。

## 覆盖端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/types/loginSessionInfo/instances` | 可选会话；回 `EMC-CSRF-TOKEN` |
| `GET` | `/api/types/system/instances` | `serialNumber` / `model` / `softwareVersion` |
| `GET` | `/api/instances/system/0` | 单实例回退 |
| `GET` | `/api/types/pool/instances` | 存储池容量 |
| `GET` | `/api/types/lun/instances` | LUN + 官方 `wwn` |
| `GET` | `/api/types/disk/instances` | 磁盘 |
| `GET` | `/api/types/ethernetPort/instances` | `macAddress`；含一条空 MAC |
| `GET` | `/api/types/fcPort/instances` | `wwn`（WWPN）；含一条空 WWPN |

列表端点支持 `page` + `per_page`，并用 `links[rel=next].href` 分页。后续 GET 必须带 Basic 与 `X-EMC-REST-CLIENT: true`。

## 启动

在 `agents/stargazer` 目录：

```bash
# HTTP，默认 127.0.0.1:18444（避开真机 443）
uv run python -m devtools.dell_unity_mock.server

# 自签 HTTPS（采集任务把 verify_tls 设为 false）
uv run python -m devtools.dell_unity_mock.server --tls --port 443
```

默认账号：`admin` / `Unity@storage`。

## 把采集任务指过来

CMDB 采集对象协议是 `dell_unity_https`（默认 443）。对 mock：

| 凭据字段 | HTTP mock | HTTPS mock |
|---|---|---|
| host / 实例 IP | `127.0.0.1` | `127.0.0.1` |
| port | `18444` | `443` |
| scheme | `http` | `https` |
| username | `admin` | `admin` |
| password | `Unity@storage` | `Unity@storage` |
| verify_tls | `false` | `false`（自签证书） |

```python
DellUnityManager({
    "host": "127.0.0.1",
    "port": 18444,
    "scheme": "http",
    "username": "admin",
    "password": "Unity@storage",
    "verify_tls": False,
})
```

curl 示例：

```bash
curl -sS -u 'admin:Unity@storage' -H 'X-EMC-REST-CLIENT: true' \
  'http://127.0.0.1:18444/api/types/system/instances?fields=id,name,model,serialNumber,softwareVersion&compact=true'
```

## 冒烟

```bash
cd agents/stargazer
uv run python -m devtools.dell_unity_mock.smoke
uv run pytest -q -o addopts='' tests/test_dell_unity_mock_smoke.py
```

CMDB 映射：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/cmdb/tests/test_dell_unity_mock_mapping.py --no-cov
```
