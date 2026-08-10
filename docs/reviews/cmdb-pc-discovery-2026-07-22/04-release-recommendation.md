# PC 发现发布建议与回滚步骤

## 发布结论：**有条件通过**

条件：上线前必须在真实 Windows 10/11（WinRM）与至少一台 macOS（SSH）目标机上
完成 `02-windows-acceptance.md` / `03-macos-acceptance.md` 清单并回填证据。
当前结论依据如下：

### 通过项（离线证据，见 01-test-evidence.md）

1. Server/Stargazer/Web 三端定向门禁全绿；PC 触及代码覆盖率 ≥75%（Stargazer 86%/87%）。
2. 端到端离线合同：任务+凭据 → headers（秘密仅 `${ENV}` 占位符）→ executor stdout
   → VM rows → 逐 PC 对账；Windows 四轮（新增/升级/完整空快照删除+审计/partial 禁删）
   与 macOS 三轮锁定，失败行零快照零删除。
3. 秘密保护回归：headers、VM labels、collect_data、format_data、ChangeRecord、
   RPC 脱敏过滤均不出现口令/PEM 私钥/密码短语原值；合同曾暴露执行器原始 msg
   回显凭据的缺口，已按已知秘密值精确脱敏并锁定。
4. 安全删除：仅完整快照 + `immediately` 策略 + 权威任务三条件同时满足才差集删除；
   partial/失败/非权威/过期策略全部禁删；删除写 DELETE_INST 审计。
5. 权威任务模型：一台 PC 同一时间只由一个任务写入/删除，冲突返回
   SOURCE_TASK_CONFLICT，移交需显式授权且完整快照落地后才切换。

### 阻断项（必须完成才能转为"通过"）

- W1–W15 Windows 真实环境验收（02 文档）；
- M1–M16 macOS 真实环境验收（03 文档），Intel/Apple Silicon 至少覆盖其一，
  另一架构明确标注；
- 目标机只读复核（注册表/文件系统采集前后无写入）。

### 已知基线问题（与本功能无关，不阻断但有风险）

- `server make test` 全量在 opspilot 测试 collection 阶段被既有故障阻断
  （`Bot doesn't declare an explicit app_label`，84 个 collection error；
  已在 PC 工作前的基线提交 4b5f447bb 复现，证据见 01 文档）；
- `web pnpm type-check` 存在既有 `src/context/locale.tsx(60,11) TS2769` 错误；
- `web pnpm lint` 存在 40 个既有错误（stories 的 storybook/no-renderer-packages
  与 ops-analysis 的 consistent-type-definitions），均不在本功能触及文件；
- `agents/stargazer make lint` 因仓库缺少 `.pre-commit-config.yaml` 无法运行
  （工具链基线缺口），已用 ruff 默认规则对 PC 触及文件做定向检查替代。

## 回滚步骤

按顺序执行，每步验证后再进行下一步：

1. **关闭企业版 PC 采集入口**：从采集对象树/许可配置中禁用 `pc` 模型入口，
   前端不再出现 PC 任务类型（新建入口关闭）。
2. **停止存量 PC 任务**：将 model_id=pc 的采集任务停用（enabled=false），
   确认 celery 节拍不再下发 PC 采集。
3. **将清理策略置 `no_cleanup`**：对所有 PC 任务执行
   `data_cleanup_strategy=no_cleanup`，确保回滚期间不发生任何差集删除。
4. **回滚 Web**：回退 PC 表单相关提交（pcTask/credentialPoolEditor/page 路由/
   API/locale），重新构建前端。
5. **回滚 Server**：回退 PC 相关 server 提交；数据库表（PCDiscoveryAuthority）
   与已发现数据保留，不做破坏性迁移。
6. **回滚 Stargazer**：回退企业版 PC 插件与 `/api/collect/pc_test_connection`
   端点；连接测试入口随 Web 回滚消失。

**明确不做**：回滚不自动删除已发现的 PC、pc_software 实例或 install_on 关联；
如需清理由管理员在 CMDB 中人工核对后执行，保留 ChangeRecord 审计轨迹。
