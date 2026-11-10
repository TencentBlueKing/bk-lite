# 01 — 修复 APM 数据面契约测试的探针下载地址

Status: ready

Blocked by: None

**What to build:** 开启 `RUN_APM_CONTAINER_CONTRACT=1` 后，`deploy/apm/tests/test_data_plane_contract.py` 全部通过；
Python SDK 片段按当前接入契约带上探针下载地址，并能在测试里真实执行。

- [ ] 弄清 `999469c6b3` 之后接入片段对 `probe_download_url` 的要求，以及片段在测试里怎样取得探针
- [ ] 测试按当前契约提供可解析的探针下载地址（必要时在测试内起一个只服务探针制品的临时 HTTP 服务）；不放宽服务端校验
- [ ] 契约测试全部通过；临时容器用独立 project 名，端口避开 4317、4318、8428、9428、10428、13133、18222、18888、18889、23133，结束后清理
- [ ] `make -C deploy/apm test validate` 仍通过

## Notes

- 本机运行着用户自己的 `bk-lite-apm-apm-*` 栈，不得停止、重建或修改。
