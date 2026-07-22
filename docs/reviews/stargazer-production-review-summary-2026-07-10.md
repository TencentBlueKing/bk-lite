# Stargazer 生产级 Review 汇总（2026-07-10）

## 范围

- 审查对象：`agents/stargazer`
- 审查协议：`docs/reviews/backend-production-review-protocol.md`
- 处理方式：每个缺陷单独开 Codex 任务修复；本文件仅汇总可提交的审查结论，`.仓库事实源/issues/` 保留为本地过程记录，不纳入业务提交。

## Findings 与修复提交

| Finding | Severity | 根因分类 | 修复提交 | 验证 |
| --- | --- | --- | --- | --- |
| 网络配置文件采集命令安全策略与实际远程执行前缀不一致，危险命令可绕过 denylist | P0 | 跨层契约不一致 / 远程执行安全风险 | `49d9e9d3d fix: 同步 Stargazer 网络配置高危命令策略` | `uv run pytest tests/test_network_config_file_info.py -q` |
| 网络配置文件空命令会被标记为成功并返回空配置 | P0 | 错误模型不清晰 / 任务失败却成功 | `32c7f3776 fix: 拒绝 Stargazer 网络配置空命令采集` | `uv run pytest tests/test_network_config_file_info.py -q` |
| IP 发现 CIDR 与目标数量缺少边界，可能一次性探测过大网段 | P0 | 资源边界缺失 | `ff346b465 fix: 限制 Stargazer IP 发现扫描规模` | `uv run pytest tests/test_ip_discovery_scanner.py tests/test_ip_discovery_targets.py -q` |
| IP 发现插件声明路径与真实模块路径不一致，按配置加载会失败 | P1 | 跨层契约不一致 | `1bf5d5e69 fix: 修正 Stargazer IP 发现插件路径` | `uv run pytest tests/test_ip_discovery_scanner.py tests/test_ip_discovery_targets.py -q` |
| NATS metrics 发布未知状态被标记为已探测投递成功 | P1 | 错误模型不清晰 / 可观测性不足 | `361f772f7 fix: 修正 Stargazer NATS 投递未知状态` | `uv run pytest tests/test_host_collector.py::TestMonitorPublishFailureHandling tests/test_host_collector.py::TestPublishMetricsToNats -q` |
| CollectionService 直接记录原始采集结果，可能泄露配置内容或命令输出 | P0 | 可观测性不足 / 敏感信息泄露 | `c771608ff fix: 脱敏 Stargazer 采集结果日志` | `uv run pytest tests/test_collection_service_logging.py -q` |
| 配置采集拆分多主机时复用首个 `instance_name`，callback 结果可能映射到错误实例 | P1 | 数据一致性 / 跨层契约不一致 | `06bf5bed3 fix: 修复 Stargazer 配置采集拆分实例映射` | `uv run pytest tests/test_api_http_layer.py -q` |

## 集成复核

已在临时集成 worktree `/private/tmp/stargazer-review-integration` 从 `feature_windyzhao` 依次 cherry-pick 7 个修复提交，未发生冲突。

合并后的聚焦回归：

```bash
uv run pytest \
  tests/test_network_config_file_info.py \
  tests/test_ip_discovery_scanner.py \
  tests/test_ip_discovery_targets.py \
  tests/test_host_collector.py::TestMonitorPublishFailureHandling \
  tests/test_host_collector.py::TestPublishMetricsToNats \
  tests/test_collection_service_logging.py \
  tests/test_api_http_layer.py \
  -q
```

结果：`84 passed, 28 warnings`。

## 未完成门禁

`make lint` 在临时集成 worktree 未能执行完成，原因是 `agents/stargazer/.pre-commit-config.yaml` 不存在，且 sandbox 阻止 pre-commit 写入用户目录日志。当前失败点是 lint 入口配置/运行环境问题，不是上述 7 个修复提交的测试失败。

## 提交建议

- 业务修复：只提交 7 个修复提交对应的代码与测试。
- 审查记录：只提交本汇总文件。
- 本地过程记录：不要提交 `.仓库事实源/summary.md`、`.仓库事实源/events.jsonl`、`.仓库事实源/issues/`、`.仓库事实源/.current_issue`、`.仓库事实源/watch.*`。
