# 中心系统 Vector

该目录只用于默认部署中的中心系统 Vector。非默认云区域、proxy、fusion-collector、采集侧 Vector、系统 Telegraf 与 webhookd 不使用这里的配置。

`bootstrap.yaml` 只声明 Vector 0.48 原生 HTTP configuration provider。部署环境必须注入：

- `SYSTEM_VECTOR_CONFIG_URL`：Server 的 `/api/v1/log/open_api/system_vector/config/` 完整地址。
- `SYSTEM_VECTOR_CONFIG_TOKEN`：`python manage.py system_vector_token` 输出的部署级 Token。
- 全量远程配置沿用默认部署已有的 `VECTOR_NATS_SERVERS`、`NATS_ADMIN_USERNAME`、
  `NATS_ADMIN_PASSWORD` 与 `VECTOR_VICTORIA_LOGS_URL` 环境变量；凭据不写入快照。

安装顺序固定为：

1. 执行数据库迁移。
2. 运行 `python manage.py system_vector_token`，保存输出并更新部署 Secret。
3. 启动 Server。
4. 携 Token 请求配置接口，确认返回 200、`X-Config-Checksum` 与 `X-Config-Generation`。
5. 使用 `bootstrap.yaml` 启动中心系统 Vector，并配置容器失败重启策略。

管理命令每次执行都会轮换 Token。若标准输出丢失，应重新执行并使用新 Token；旧 Token 会立即失效。
