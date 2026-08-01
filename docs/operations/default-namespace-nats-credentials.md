# 默认命名空间 NATS 凭据升级

默认命名空间不再为缺失或畸形的 NATS 配置生成账号密码。地址和凭据必须由部署
环境显式注入，配置错误不会写入或覆盖 `NameSpace`。

## 影响盘点

- `startup.sh` 通过 `batch_init` 调用 `init_default_namespace`。默认命名空间是
  运营分析的可重建外部数据源配置，不是 Server 核心进程的启动硬依赖。
- 手工执行 `python manage.py init_default_namespace` 时，非法配置会返回
  `CommandError`；生产 `batch_init` 会记录包含异常类型和原因的告警并继续启动。
  修复配置后重跑 `python manage.py batch_init --apps=operation_analysis`，可从标签已
  创建、数据源未创建等部分状态继续完成初始化。
- 纯 `host:port` 与不含凭据的 `nats://host:port` 仍受支持，账号密码分别读取
  `NATS_USER` 和 `NATS_PASSWORD`。带账号密码的完整 `nats://` / `tls://` URL
  仍受支持。
- 平台 NATS 客户端仍可使用 `NATS_TOKEN`，但运营分析 `NameSpace` 模型只支持
  user/password。token-only 部署不会再生成不可用的弱账号；Server 会继续启动，
  运营分析默认命名空间需另行配置 user/password。
- 已存在的默认命名空间会在配置有效时原位更新，主键及其与数据源的关联保持
  不变；重复执行不会新增记录。配置无效时存量记录保持不变。

## 升级与轮换

1. 升级前确认 NATS 已创建供 BK-Lite 使用的非默认账号，并在部署系统中注入
   `NATS_USER`、`NATS_PASSWORD`。不要把真实凭据写入仓库中的 example 文件。
2. `NATS_SERVERS` 推荐只配置 `host:port`；如需兼容旧镜像回滚，也可暂时配置
   带 percent-encoded 账号密码的完整 URL。
3. 在升级窗口执行 `python manage.py batch_init --apps=operation_analysis`。默认命名
   空间成功后会原位轮换存量凭据，并补齐内置数据源；失败时不会写入命名空间，
   按告警修复环境变量后重跑同一命令。
4. 在运营分析的数据源预览中验证默认命名空间连接，再重启或继续发布。
5. 确认新凭据生效后，在 NATS 服务端撤销旧的弱账号密码。

## 回滚

代码可回滚到上一镜像，数据库无需逆向迁移。回滚前把 `NATS_SERVERS` 临时设为
包含新账号密码的完整 URL，使旧版本也读取同一组已轮换凭据；不要恢复旧弱凭据。
回滚后再次运行 `python manage.py batch_init --apps=operation_analysis` 并验证数据源连接。
