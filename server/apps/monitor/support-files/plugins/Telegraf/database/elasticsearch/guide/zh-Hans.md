# ElasticSearch 监控接入指南

本能力通过 Telegraf `inputs.elasticsearch` 访问 ElasticSearch HTTP API，采集集群健康和指定节点统计。

## 前置要求

- 采集节点能够访问 ElasticSearch 的完整 HTTP(S) 地址。
- 准备可读取集群健康与节点统计接口的用户名和密码；当前页面两项均为必填。
- 带认证的端点应优先使用 HTTPS，并部署证书链受采集节点信任的服务端证书。
- 若目标只能使用 HTTP，仅可部署在隔离且可信的链路中；Basic Auth 凭据只是可逆编码，会在网络中以未加密形式传输。
- 账号至少能访问 `/_cluster/health` 与 `/_nodes/stats`。
- 当前模板固定启用集群健康，并采集 JVM、文件系统、进程、断路器、HTTP 和线程池节点统计。
- HTTPS 连接在当前模板中固定跳过服务端证书校验，页面不提供 CA 或校验开关；不要因此把不可信证书作为常规方案。

## 接入步骤

1. 从实际采集节点验证完整服务器地址、账号和接口权限。
2. 填写服务器地址、用户名、密码和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写服务器地址、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

以下 HTTPS 命令会交互式询问密码，不会把密码写入命令行参数或历史记录。交互提示不能保护网络传输；安全性仍依赖 TLS，证书链必须受采集节点信任。不要将 `-k` 或 `--insecure` 作为常规方案：

```bash
curl --fail --silent --show-error --user monitor "https://es.example.com:9200/_cluster/health"
curl --fail --silent --show-error --user monitor "https://es.example.com:9200/_nodes/stats"
```

两个请求都应返回 `200`；`--fail` 会保留 `4xx/5xx` 失败状态。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 服务器地址 | 是 | 完整 HTTP(S) URL，带认证时优先使用 `https://es.example.com:9200`。 |
| 用户名 | 是 | 可读取集群健康和节点统计接口的账号。 |
| 密码 | 是 | 对应账号密码。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 ElasticSearch 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `elasticsearch_cluster_health_status_code`
- `elasticsearch_cluster_health_active_primary_shards`
- `elasticsearch_jvm_mem_heap_used_percent`
- `elasticsearch_thread_pool_search_queue`

## 常见问题

### 返回 `401` 或 `403`

- 核对用户名、密码以及两个接口的读取权限。
- 分别验证集群健康与节点统计；其中一个成功不能证明另一个有权限。

### HTTPS 连接异常

- 核对 URL 协议与端口。
- 当前模板固定跳过服务端证书校验，但不支持客户端证书或自定义 CA 字段；要求双向 TLS 的目标不能直接接入。

### 只有部分数据

- 节点统计只包含模板列出的六类，未配置的统计类别不会采集。
- 检查 Telegraf 日志中是集群健康请求还是具体节点统计请求失败。
