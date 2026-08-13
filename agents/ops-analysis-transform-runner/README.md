# Ops-Analysis Transform Runner

独立薄 Runner：只接收 `{script, rows, params, org_id}`，执行 `transform(rows, params) -> list[dict]`。

Runner **不持有**数据库凭据、REST Headers、Django 配置或用户 Token。AST/import 白名单只收窄脚本能力，**不是**安全边界；生产靠网络隔离、服务间认证与可杀进程。

## V1 部署约束

- **单副本 + 单 uvicorn worker**（`--workers 1`）。扩容前不要水平扩展，否则组织并发 3 会按副本数放大。
- **服务间认证**：`TRANSFORM_RUNNER_TOKEN` 必填；Server 使用相同值调用。
- **端口**：本地 Compose 仅绑定 `127.0.0.1:8099`；生产不要发布公共宿主机端口，仅让 Server 所在内部网络访问。
- **出站**：默认禁止业务网/公网出站（生产用 internal network / 无默认路由）。
- **非关键依赖**：不参与 Server `batch_init`；不可用时有脚本 REST 明确失败，Excel 保留旧成功结果。

## 本地启动

```bash
cd agents/ops-analysis-transform-runner
export TRANSFORM_RUNNER_TOKEN=dev-transform-token
docker compose -f support-files/docker-compose.yml up --build
```

健康检查：`curl http://127.0.0.1:8099/healthz`

Server 侧：

```bash
export TRANSFORM_RUNNER_URL=http://127.0.0.1:8099
export TRANSFORM_RUNNER_TOKEN=dev-transform-token
```

## 契约

- `POST /v1/transform`（`Authorization: Bearer <token>` 或 `X-Transform-Token`）
- 允许 import：`json` / `math` / `datetime` / `collections`
- 输入/输出最多 10000 行，序列化上限由 `TRANSFORM_MAX_PAYLOAD_BYTES` 配置（默认 8MB）；超时默认 5s（子进程 kill/reap）；同组织默认并发 3（忙则 429，不排队）

## 安全说明

容器非 root、只读根文件系统、drop capabilities、CPU/内存/PID/tmpfs 上限。每次脚本在独立子进程中执行，超时真正终止。功能开关仅用于故障熔断，不能替代上述门槛。
