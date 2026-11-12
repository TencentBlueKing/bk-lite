# 01 — 修复 APM 数据面契约测试的探针下载地址

Status: done

Blocked by: None

**What to build:** 开启 `RUN_APM_CONTAINER_CONTRACT=1` 后，`deploy/apm/tests/test_data_plane_contract.py` 全部通过；
Python SDK 片段按当前接入契约带上探针下载地址，并能在测试里真实执行。

- [x] 弄清 `999469c6b3` 之后接入片段对 `probe_download_url` 的要求，以及片段在测试里怎样取得探针
- [x] 测试按当前契约提供可解析的探针下载地址（必要时在测试内起一个只服务探针制品的临时 HTTP 服务）；不放宽服务端校验
- [x] 契约测试全部通过；临时容器用独立 project 名，端口避开 4317、4318、8428、9428、10428、13133、18222、18888、18889、23133，结束后清理
- [x] `make -C deploy/apm test validate` 仍通过

## Notes

- 本机运行着用户自己的 `bk-lite-apm-apm-*` 栈，不得停止、重建或修改。

## Completion evidence

Python host 片段从 `probe_download_url` 下载 `opentelemetry-python-wheels.tar.gz`，校验服务端算出的 SHA-256，再 `tar` 解压后离线 `pip install`。契约测试在 `127.0.0.1` 的空闲端口起一个只提供该路径的 HTTP 服务，制品是测试内构造的最小 wheelhouse。SHA-256 仍走 `get_probe_artifact_sha256`，对象存储读取被换成同一份字节，避免连接或写入本机 NATS。片段的下载、校验和解压真实执行；`pip install` 不执行，SDK 发射仍使用 server 虚拟环境里已安装的 OpenTelemetry。服务端对空 `probe_download_url` 的拒绝没有改动。

- 契约测试：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb APM_NATS_IMAGE=public.ecr.aws/docker/library/nats:2.10.25 APM_NATS_BOX_IMAGE=bk-lite.tencentcloudcr.com/bklite/natsio/nats-box:latest RUN_APM_CONTAINER_CONTRACT=1 timeout 900 uv run pytest -q ../deploy/apm/tests/test_data_plane_contract.py -s --no-cov -o addopts= -p no:cacheprovider`。退出码 0，`1 passed, 4 warnings in 118.46s`。project 名为 `bk-lite-apm-contract-<pid>`。
- `timeout 900 make -C deploy/apm test validate`：退出码 0。三个 Go 包为 cached ok。`compose config --quiet` 通过。镜像仍是 `bklite/apm-otel-collector:0.153.0-bklite.2`（`sha256:e04a3c62f2e5`，构建缓存命中，标签未换成新镜像）。`system.yaml` 在写入地址为空时报 `invalid endpoint`，分片为空时报 external labels 为空。
- 结束后 `docker ps -a --filter name=bk-lite-apm-contract`、对应 network 和 volume 都为空。用户的 `bk-lite-apm-apm-*` 与 `bklite-dev-*` 容器仍在运行。
