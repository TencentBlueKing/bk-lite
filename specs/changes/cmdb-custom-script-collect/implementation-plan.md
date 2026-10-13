# 实施方案与流程：CMDB 自定义脚本采集

依据：[spec.md](spec.md)（设计基准，D1–D11 + 否决记录 1–10）。
状态：M0–M6 已按本方案落地（2026-10-10）。任务表单复用 Linux SSH / Windows WinRM 表单并提交插件引用；业务凭据字段的表单录入仍走 API。

## 总体策略

- **先 Server 后 Stargazer 再前端**：RPC 契约、headers 契约、指标命名都由 Server
  定义，Stargazer 按契约消费；前端依赖 Server API。
- **每个里程碑独立可验证、可提交**：按模块边界切分，每步带测试与验收标准，
  不跨里程碑留半成品；里程碑内先写测试锚定契约（新增行为测试先行，回归测试
  锁旧行为）。
- **只改任务范围**：不动工作区既有未提交内容，不做无关格式化。

## 里程碑总览与依赖

```
M0 前置确认 ──┬─→ M1 插件库 ──→ M2 任务接入 ──→ M3 RPC+入库 ──→ M4 Stargazer ──→ M6 E2E
              │                    │
              └────────────────────┴─→ M5 前端（依赖 M1/M2 的 API，可与 M3/M4 并行）
```

---

## M0 前置确认（2026-10-10 已确认）

| # | 结论 |
|---|---|
| 0.1 | **社区版部署带 ansible-executor，本功能是社区版功能**。Windows WinRM 路由放 `agents/stargazer/plugins/inputs/custom_script/`，不进 enterprise 目录 |
| 0.2 | **业务凭据要接凭据库**。加密字段按字段直填或引用已有凭据的一个秘密字段；下发时解析，明文不落库（spec D10）。传输凭据继续走凭据池既有双模式 |

基线验证：实施开始前跑一遍将被触碰模块的现有测试，留存基线结果
（`test_collect_management_service` / `test_collect_views_actions` /
`test_collect_model_credential_pool` / stargazer `test_async_plugin_contract` 等）。

---

## M1：Server 插件库（数据层 + API）

**改动**（全部 Server）：

1. `models/custom_collect_plugin.py`（新）+ migration：字段按 spec §3.1，
   `plugin_id` 唯一索引；
2. 插件库 serializer + view（新）：CRUD、校验链（plugin_id 正则
   `^custom_[a-z0-9_]{2,40}$` 且全局唯一、content ≤64KB/UTF-8、shell×os_type、
   credential_schema 形状与保留字清单、锁定字段有引用时拒改）、
   **删除保护**（被 `CollectModels` 引用时 409）；urls 注册；
3. 组织隔离：queryset 按 team 过滤，复用 `CollectModels` 的组织过滤语义；
4. 审计：create/update 走 `create_change_record`，快照仅 version + checksum；
5. 模型删除校验：模型删除入口增加"被自定义插件绑定则阻止"。

**测试**：spec §9 插件库行 + 组织隔离行（双组织用例）。

**验收**：插件 CRUD API 可用；双组织隔离测试通过；删除保护（插件被任务引用、
模型被插件绑定）两条链路测试通过；审计快照断言无正文。

---

## M2：Server 任务接入（类型 + 下发 + 凭据）

**改动**：

1. `constants/constants.py`：`CollectPluginTypes.CUSTOM_SCRIPT`；
2. `services/collect_object_tree.py`："自定义"分组动态 children（§3.5，
   按请求用户组织过滤；`credential_type_keys` 按 os_type）；
3. `node_configs/custom_script.py`（新）：`CustomScriptNodeParams` 哨兵键注册；
   `set_credential()` 双 OS（windows 含 `node_id`）；`env_config()` schema 驱动；
   headers 追加 `cmdbcustom_plugin_id / cmdbos_type / cmdbshell`，业务凭据
   `cmdb<key>`（加密字段 env 间接引用）；
4. `node_configs/config_factory.py` + `node_configs/base.py`：候选键按
   task_type 构造（custom_script → 哨兵键）；
5. 凭据：`get_collect_model_passwords` 链路 task_type 分支（传输固定集 ∪
   schema encrypted keys）；`params.custom_credential_values` 直填值显式加密
   （D10）；vault 引用只存 ID/字段/服务端 actor context，下发时
   `resolve_credential` 解析进 env，明文不写回；
6. `services/collect_service.py` + `serializers/collect_serializer.py`：
   任务 create/update 校验（插件存在、组织范围内、`model_id` 与插件一致）；
7. **§5.4 开关点审计**：逐项核对 `celery_tasks.py` / `collect_service.py` /
   `collection_offset_policy.py` 的 task_type 分支，核对结论写入 PR 描述。

**测试**：spec §9 凭据行、Server 下发行、生命周期行。

**验收**：可创建自定义任务并生成正确的双 OS 节点配置 headers；密码/加密字段
保存后全部 `enc:` 前缀；内置任务（host/nginx 等）工厂与下发行为回归通过。

---

## M3：Server NATS RPC + 入库格式化

**改动**：

1. `nats/nats.py`：`cmdb_get_custom_script` responder（存在性/类型校验、
   返回 DB 最新版、不记录 content）；
2. `collection/plugins/registry.py`：`"*"` 通配回退（精确优先）；
3. `collection/plugins/community/custom_script/generic.py`（新）：
   `CustomScriptCollectionPlugin`——动态 `_metrics`（经任务解析插件取
   `{plugin_id}_info_gauge`）、模型属性白名单透传、类型转换、
   inst_name 缺失丢弃计数。

**测试**：spec §9 Server RPC 行、Server 入库行、Server 共存行
（内置 + 两个自定义插件同指向 host 的三路隔离）。

**验收**：给定构造的 VM 返回数据（fixture），同步链路产出正确
`{model_id: [records]}` 并经 `MetricsCannula` 入库；共存用例通过。

---

## M4：Stargazer 执行链

**改动**（全部 `agents/stargazer`）：

1. `plugins/script_executor.py`：`SSHPlugin` 增加 `script_content`（跳过
   `_read_script`，shell 从参数取）与可选 `execute_timeout`（默认 60 不变，
   `nats_timeout` 随既有公式放大）；
2. `core/plugin/executor.py`：`script_source: remote` 跳过 script_path 注入；
3. `core/collection/plugins.py`（`UnifiedPluginFactory`）：custom_script Run
   准备期一次 RPC 拉脚本注入 Run 参数；拉取失败 → Run 以
   `SCRIPT_FETCH_FAILED` 快速失败，不进目标调度；
4. `plugins/inputs/custom_script/plugin.yml` + `collector.py`（新，社区目录）：
   `CustomScriptCollector`——入参校验、占位符渲染（`{{bk_host_innerip}}` /
   `{{credential.<key>}}`）、双 OS 路由（linux → SSHPlugin；windows →
   `ansible_adhoc`/winrm，M0.1 结论决定放社区或企业目录）、输出边界
   （4MB/5000/1024 截断降级）、稳定错误码与 `_scrub_secrets` 脱敏、
   `{"result": {plugin_id: records}}` 返回。

**测试**：spec §9 Stargazer 行（合同测试、Run 准备期注入语义、双路由 mock、
execute_timeout 透传与 60s 默认回归、边界截断、错误码、script_content/
script_path 双分支回归）。

**验收**：`uv run pytest -q -o addopts='' tests/test_async_plugin_contract.py
<新增测试>` 通过；既有 job 插件测试回归通过。

---

## M5：Web 前端（依赖 M1/M2 API，可与 M3/M4 并行）

**改动**（全部 `web/src/app/cmdb`）：

1. 自定义插件管理页（新）：列表（名称/plugin_id/模型/OS/版本/引用数/时间）、
   在线编辑器 + 上传填充 + 预览确认保存、受影响任务数提示、凭据 schema
   表单化编辑、输出契约文档内嵌；
2. 模型详情"自定义采集"tab（`assetManage/management/detail`，与 attributes
   平级）：按 model_id 过滤 + 预填锁定创建；
3. 任务创建表单：消费动态树节点（与内置对象同构），业务凭据字段按 schema
   追加渲染；
4. `locales/zh.json` / `en.json` 文案。

遵守 Web UI 硬约束（Tailwind、语义 token、AntD 优先；复用实体列表卡与
详情页既有模式）。

**测试**：`pnpm lint` + 相关 `pnpm test:*`；改布局/类型后 `pnpm type-check`。

**验收**：插件全生命周期（建→编辑→引用→删保护）与任务创建流程页面可走通。

---

## M6：E2E 收尾

1. E2E fixture 流水线测试（参照 `tests/e2e/test_hdfs_pipeline.py`）：
   脚本输出 → prometheus 格式 → format → 入库断言，覆盖 linux 单链路；
2. 全量回归：M1–M5 全部新增测试 + 基线测试复跑；
3. spec 状态更新（draft → implemented，记录偏差）；按需补
   `docs/changelog/`。

**最终验收清单**（对照 spec）：

- [ ] 插件库 CRUD + 组织隔离 + 双重删除保护 + 审计无正文
- [ ] 任务创建→节点配置下发双 OS headers 契约正确、密码全加密
- [ ] Run 准备期一次 RPC、全目标同版本、失败快速终止
- [ ] linux SSH/本地 + windows WinRM 双路由（范围视 M0.1）
- [ ] `{plugin_id}_info_gauge` 指标隔离、动态白名单入库、下游对账零改动验证
- [ ] 同模型三路共存（内置 + 两自定义）互不干扰
- [ ] 全部 §9 测试通过 + 既有基线无回归

---

## 里程碑提交节奏

每个里程碑一次独立提交（中文提交信息），PR 描述附该里程碑的测试输出与
§5.4 审计结论（M2）。实施中发现与 spec 冲突的代码事实，先回 spec 修订
决策记录再继续，不在代码里静默偏离。
