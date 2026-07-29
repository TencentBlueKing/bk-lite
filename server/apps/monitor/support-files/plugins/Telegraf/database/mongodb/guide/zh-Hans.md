# MongoDB 监控接入指南

## 前置要求

- 目标 MongoDB 服务已启动，默认可访问 `27017` 端口。
- 采集节点到 MongoDB 地址网络可达（含安全组 / 防火墙放通）。
- 已确认是否启用鉴权：未启用鉴权时用户名、密码可为空；启用鉴权时需准备可读取 `serverStatus`、`dbStats` 等监控接口的账号。
- Telegraf `inputs.mongodb` 通过 `mongodb://user:pass@host:port/?connect=direct` 形式的连接串直连，无需额外部署 exporter。

## 推荐账号权限

启用鉴权时，建议为监控单独创建一个只读账号，至少具备以下角色：

- `clusterMonitor`：读取 `serverStatus`、`replSetGetStatus` 等集群级指标。
- `read`（作用于目标库）或对应库的 `dbStats`/`collStats` 读权限。

创建示例（mongosh 中执行，启用分片 / 多业务库时按需扩展）：

```javascript
db.getSiblingDB("admin").createUser({
  user: "monitor",
  pwd: "<password>",
  roles: [
    { role: "clusterMonitor", db: "admin" }
  ]
})
```

未启用鉴权时可将用户名、密码留空，模板会自动拼接无凭据连接串。

## 接入步骤

1. 在采集节点上确认可访问目标 MongoDB（可参考下方校验命令）。
2. 在监控对象接入页填写主机、端口（默认 `27017`）、采集间隔（默认 `60s`）。
3. 若实例启用了鉴权，填写对应的用户名与密码；未启用则留空。
4. 在「监控对象」表格中填写节点、主机、端口、实例名称与所属组。
5. 点击「确认」保存配置，等待至少一个采集周期。
6. 到资产或指标页确认实例已上报数据。

## 接入前校验

无认证直接连通性：

```bash
mongosh "mongodb://<host>:<port>" --eval "db.serverStatus().ok"
```

带认证：

```bash
mongosh "mongodb://<user>:<password>@<host>:<port>" --eval "db.serverStatus().ok"
```

若仅希望确认网络端口可达（不依赖 mongosh 客户端）：

```bash
nc -vz <host> 27017
```

满足以下条件可认为端点基本可用：

- `db.serverStatus().ok` 返回 `1`。
- 端口 `27017` 在采集节点上可达。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | 启用鉴权时填写，未启用可留空 |
| 密码 | 否 | 与用户名对应的登录密码，未启用鉴权可留空 |
| 主机 | 是 | MongoDB 服务地址，例如 `10.0.0.10` |
| 端口 | 是 | MongoDB 端口，默认 `27017` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 在采集节点重新执行 `mongosh` / `nc -vz` 校验命令，确认不是仅控制台可达。
- 等待至少一个采集间隔后再查看。
- 检查节点上 Telegraf / 采集任务是否正常运行。
- 确认实例的防火墙或安全组已对采集节点 IP 放通 `27017`。

### 2. 认证失败

- 确认用户名密码无首尾空格与特殊字符转义问题。
- 确认账号具备 `clusterMonitor` 角色，能够读取 `serverStatus`。
- 若 MongoDB 启用了 SCRAM / x.509 等额外鉴权方式，需与运维确认采集端支持的鉴权方式。
- 启用鉴权但模板未带凭据时，采集会回退为匿名连接，请勿将用户名密码留空。

### 3. 仅部分指标缺失或权限不足

- `mongodb` 指标（连接数、副本集状态等）依赖 `serverStatus`，无 `clusterMonitor` 时该组指标可能为空。
- 数据库级指标（`dbStats`）依赖对目标库的 `read` 权限，请按需为账号授权。
- 业务库名差异较大时，可在指标页通过 `database_name` 标签过滤确认实际采集到的库。