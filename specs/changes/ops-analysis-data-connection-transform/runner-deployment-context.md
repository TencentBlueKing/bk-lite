# 运营分析 Transform Runner 部署上下文

运营分析新增独立服务 `ops-analysis-transform-runner`，用于执行 REST/Excel 数据源的 Python 转换脚本。具体流水线和部署方式由运维按现有规范处理。

关联变更：[`c24c1345`](https://github.com/hongxixixi/bk-lite/commit/c24c1345a734c4fb598b43941c0eb5515dd2d77d)

## 构建信息

- 构建上下文：`agents/ops-analysis-transform-runner`
- Dockerfile：`agents/ops-analysis-transform-runner/support-files/Dockerfile`
- 内部端口：`8099`

## 环境变量

配置示例（示例 Token 不可用于生产）：

```env
# Runner
TRANSFORM_RUNNER_TOKEN=example-only-change-me
TRANSFORM_ORG_CONCURRENCY=3
TRANSFORM_TIMEOUT_SECONDS=5
TRANSFORM_MAX_PAYLOAD_BYTES=8388608

# Server API 和默认 Celery Worker
TRANSFORM_RUNNER_URL=http://ops-analysis-transform-runner:8099
TRANSFORM_RUNNER_TOKEN=example-only-change-me
TRANSFORM_RUNNER_TIMEOUT=8
```

- `TRANSFORM_RUNNER_TOKEN`：服务认证密钥，由 Secret 管理，Runner、Server API 和默认 Celery Worker 使用同一个值；
- `TRANSFORM_ORG_CONCURRENCY`：单个组织最多同时执行 3 个转换任务；
- `TRANSFORM_TIMEOUT_SECONDS`：脚本最多执行 5 秒；
- `TRANSFORM_MAX_PAYLOAD_BYTES`：输入、输出分别最多 8 MiB；
- `TRANSFORM_RUNNER_URL`：Runner 的内部访问地址；
- `TRANSFORM_RUNNER_TIMEOUT`：Server/Celery 调用 Runner 最多等待 8 秒。

## 部署约束

- 固定单副本、单 Uvicorn Worker，不得水平扩容；
- 不开放公网或宿主机端口，只允许 Server API 和默认 Celery Worker 通过内部网络访问 `8099`；
- Runner 禁止访问公网和业务网络，不注入数据库、REST Headers 等业务凭据；
- 非 root、只读根目录、禁止权限提升并删除全部 Linux capabilities；
- 限制为 `1 CPU`、`512 MiB` 内存、`128 PID`，`/tmp` 使用 `64 MiB` tmpfs；
- Runner 不参与 Server `batch_init`，不可用时不能阻断 Server 启动。

## 部署确认

- `GET /healthz` 返回 `status=ok`、`auth_configured=true`、`org_concurrency=3`；
- Server API 和默认 Celery Worker 均能通过内部服务名访问 Runner；
- 正确 Token 可以调用转换接口，缺少或错误 Token 时返回 401；
- Runner 无公网、业务网络出站能力，外部无法访问其 `8099` 端口。
