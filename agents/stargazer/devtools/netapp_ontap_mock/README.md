# NetApp ONTAP REST mock

**TEST-ONLY / 本地联调**，不进默认生产采集路径，不改任务树默认值，不碰 FDB / `interface_connect_*` / mapping / canvas。
语义对齐 `netapp_ontap_https`：HTTP Basic，`base_path=/api`。无 MAC / 无 WWPN 原样返回，采集映射跳过，**不编造**身份。

ONTAP LUN REST 对象没有稳定 `wwn`/`naa` 字段；夹具只保留官方 `serial_number`，**不会**把序列号换算成 NAA。

## 覆盖端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/cluster` | 集群名 / uuid / version.full |
| `GET` | `/api/cluster/nodes` | 可选节点型号 / 序列号 |
| `GET` | `/api/network/ethernet/ports` | `mac_address`；含一条空 MAC |
| `GET` | `/api/network/fc/ports` | 稳定 REST `wwpn`；含一条空 WWPN |
| `GET` | `/api/storage/aggregates` | 存储池（aggregate） |
| `GET` | `/api/storage/disks` | 磁盘 |
| `GET` | `/api/storage/volumes` | FlexVol |
| `GET` | `/api/storage/luns` | LUN（无臆造 WWN） |
| `GET` | `/api/network/ip/interfaces` | 仅回填以太口 IPv4，不建 LIF 模型 |

列表端点支持 `max_records` + `offset`，并用 `_links.next.href` 分页。后续 GET 必须带 Basic。

## 启动

在 `agents/stargazer` 目录：

```bash
# HTTP，默认 127.0.0.1:18443（避开真机 443）
uv run python -m devtools.netapp_ontap_mock.server

# 自签 HTTPS（采集任务把 verify_tls 设为 false）
uv run python -m devtools.netapp_ontap_mock.server --tls --port 443
```

默认账号：`admin` / `Netapp@storage`。

## 把采集任务指过来

CMDB 采集对象协议是 `netapp_ontap_https`（默认 443）。对 mock：

| 凭据字段 | HTTP mock | HTTPS mock |
|---|---|---|
| host / 实例 IP | `127.0.0.1` | `127.0.0.1` |
| port | `18443` | `443` |
| scheme | `http` | `https` |
| username | `admin` | `admin` |
| password | `Netapp@storage` | `Netapp@storage` |
| verify_tls | `false` | `false`（自签证书） |

Stargazer 插件直接调：

```python
NetAppOntapManager({
    "host": "127.0.0.1",
    "port": 18443,
    "scheme": "http",
    "username": "admin",
    "password": "Netapp@storage",
    "verify_tls": False,
})
```

curl 示例：

```bash
curl -sS -u 'admin:Netapp@storage' 'http://127.0.0.1:18443/api/cluster'
```

## 冒烟

```bash
cd agents/stargazer
uv run python -m devtools.netapp_ontap_mock.smoke
uv run pytest -q -o addopts='' tests/test_netapp_ontap_mock_smoke.py
```

CMDB 映射（空 MAC/WWPN 跳过 + `storage contains` 口）用同一套夹具：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/cmdb/tests/test_netapp_ontap_mock_mapping.py --no-cov
```

采集侧原始回包保留无 MAC / 无 WWPN 的口；CMDB `format_metrics` 按身份跳过。有身份的口写 `storage_contains_storage_eth_port` / `storage_contains_storage_fc_port`。
