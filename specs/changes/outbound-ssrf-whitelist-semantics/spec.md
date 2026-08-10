# 出站 SSRF 白名单语义重对齐

Status: implemented

## Completion Evidence

- `SSRFValidator.validate` 已改为：公网域名默认通；黑名单网段需 CIDR 或域名全等例外；纯 IP 必 CIDR；云 metadata 硬挡；`validate_llm_endpoint` / `validate_callback` 未改。
- Webhook `is_valid_webhook_url` 委托统一 `validate`。
- 迁移 `0044_remove_builtin_webhook_domains` 删除四条公有云内置域名种子。
- 管理端 zh/en 文案已按新语义更新。
- 行为覆盖测试：`apps/core/tests/utils/test_outbound_ssrf_semantics_coverage.py`（seam：validate / webhook / cache / 0044）。
- 验证（`--cov-fail-under=80`）：
  - `ssrf_validator.py` 94%
  - `network_whitelist_cache.py` 100%
  - `0044_remove_builtin_webhook_domains.py` 100%
  - **TOTAL 95%**；`107 passed`（`-m "not django_db"`）。

## Problem Statement

系统管理中的网络白名单与通道（群聊小助手）webhook 校验当前采用「域名白名单等值放行，否则全部解析 IP 必须落在 CIDR 白名单」的严格放行模型。这导致：

1. 公有云官方 IM webhook（企微 / 飞书 / 钉钉等）依赖内置域名行或等价配置才能通过，语义过死；
2. 私有化企微等场景 webhook 填的是内网域名，DNS 常返回多个内网 A 记录，若只靠 CIDR，管理员要维护大量 IP；
3. 通道侧 `is_valid_webhook_url` 与核心 `SSRFValidator.validate` 是两套策略：前者偏「总白名单」，后者偏「黑名单 + CIDR 例外」，行为不一致，运维与安全边界难以统一解释。

管理员期望：公网目标默认可用；内网 / 危险地址默认拦截；私有化域名用「域名例外」一次覆盖多 IP，而不是把 App 做成企业 DNS 治理工具。

## Solution

将出站校验统一到 `SSRFValidator.validate` 的黑名单优先模型，Webhook 复用同一套逻辑；`NetworkWhiteList` 保留 CIDR 与域名两种条目，但域名条目的语义收窄为「主机名全等命中后，对该次解析得到的内网 / 黑名单网段地址视为已授权例外」，不再表示「名字匹配即跳过一切 IP 检查」。

判定摘要：

1. 固定危险主机名（localhost、云 metadata 主机名等）直接拒绝。
2. 纯 IP（含可识别的字面量变形与 IPv6）：必须命中 CIDR 白名单；云 metadata 等硬黑名单不可被白名单覆盖。
3. 域名：解析 DNS 后——硬黑名单拒绝；落在普通黑名单网段时，域名白名单全等命中则放行，否则须 CIDR 例外；公网默认放行。
4. 删除四条公有云内置域名种子（公网默认已通）。`validate_llm_endpoint` 与 `validate_callback` 保持现有宽松语义不动。
5. 上线硬切换，不做存量纯 IP 配置的自动迁移或双轨开关。

## User Stories

1. As an 管理员配置公有云企微 / 飞书 / 钉钉 webhook, I want 使用官方公网域名时无需再维护白名单条目, so that 通道测试与发送默认可用。

2. As an 管理员对接内网私有化企微, I want 只把 webhook 主机名加入域名白名单, so that 该域名解析出的多个内网 IP 不必逐条填 CIDR。

3. As an 管理员需要放行特定内网或公网字面量 IP 出站, I want 在 CIDR 白名单中登记对应网段或地址, so that 纯 IP URL 与未进域名例外的内网域名都能按规则放行。

4. As an 安全负责人, I want 云 metadata 与同类硬黑名单目标即使在白名单中也不可达, so that 管理员误配或被绕过时仍有底线。

5. As an OpsPilot / 通用出站调用方, I want 与通道共用同一套 `validate` 语义（含域名内网例外与纯 IP 必白名单）, so that 系统级网络白名单表的行为可预期。

6. As an LLM 端点或 job 回调配置者, I want `validate_llm_endpoint` / `validate_callback` 行为保持不变, so that 内网 LLM 与内部回调不被本变更误伤。

## Implementation Decisions

### 校验统一

- Webhook 出站（企微 / 飞书 / 钉钉机器人、自定义 webhook，含通道「测试」）改为走统一的 `SSRFValidator.validate` 语义，不再维护独立的「域名匹配即放行，否则全部 IP 必须在 CIDR」分支作为主路径。
- 现有 `validate(url, allowlist=...)` 参数语义是「若传入则仅允许这些域名」，与本变更的「域名表 = 内网例外」不同；不得复用该参数表达新语义。新语义通过读取系统网络白名单缓存中的 domains / cidrs 在 `validate` 主路径内实现。
- `validate_llm_endpoint`、`validate_callback` 本变更不修改。

### 判定顺序（`validate`）

1. 仅允许 `http` / `https`；拒绝空 host、非法 URL 形态。
2. 主机名落在固定危险主机名集合（含 localhost 类与云 metadata 主机名）→ 拒绝。
3. 若 host 为纯 IP 字面量（含库可识别的变形与 IPv6 字面量）→ 必须落在 CIDR 白名单；若同时命中硬黑名单（云 metadata 等）→ 仍拒绝。
4. 若 host 为域名 → DNS 解析；任一对解析 IP：
   - 命中硬黑名单 → 拒绝（域名白名单不可覆盖）；
   - 命中普通黑名单网段（沿用现有 `BLOCKED_NETWORKS`）→ 仅当主机名与域名白名单全等（小写）命中，或该 IP 落在 CIDR 白名单时放行；
   - 否则（公网）→ 放行。
5. 多 A/AAAA：每一次发送 / 校验都重新解析；任一不合格 IP 导致整次拒绝。

### 黑名单与白名单数据

- 普通 IP 黑名单：沿用现有 `SSRFValidator.BLOCKED_NETWORKS`（含 RFC1918、回环、链路本地、CGNAT、文档网段、相关 IPv6 特殊段等），Webhook 与 OpsPilot 等 `validate` 调用方共用一张表。
- 硬黑名单：云 metadata 地址 / 网段（及既有主机名集合）优先于 CIDR 与域名例外。
- CIDR 白名单：允许任意合法 CIDR（用于内网例外与「纯 IP 必白名单」，含公网纯 IP）；继续拒绝 `0.0.0.0/0` 与 `::/0`。
- 域名白名单：保留字段与管理 UI；匹配为小写全等，或 `*.example.com` 前缀通配（后缀匹配，含多级子域，不含 apex 根域）；禁止 `*` / `*.com` / 中间通配；条目互斥规则（单行 CIDR 与域名二选一）可保持现有产品形态。
- 缓存继续一次加载 cidrs + domains；写路径主动失效。

### 内置数据与产品文案

- 数据迁移或初始化步骤删除 / 停用四条公有云内置域名（`qyapi.weixin.qq.com`、`open.feishu.cn`、`open.larksuite.com`、`oapi.dingtalk.com`）的 `is_build_in` 种子；校验不再依赖它们。
- 管理端文案需说明：域名条目仅在「解析到黑名单网段（含内网）」时作为例外；公网域名无需配置；纯 IP URL 必须配置 CIDR。
- 上线策略：硬切换。不做扫描回填、双轨开关或自动把存量纯 IP 写入白名单；未加白的纯 IP 配置将失败，由发布说明告知。

### 错误契约

- 因未在白名单而拒绝、且可通过加白名单修复的失败，继续使用既有 `NETWORK_WHITELIST_REQUIRED` 类错误载荷（含跳转网络白名单的引导），避免泄露过多内部拓扑。
- 硬黑名单拒绝使用不可通过加白名单绕过的错误语义（与现有 metadata 硬挡一致）。
- 服务端日志记录 hostname 与解析 IP 列表，便于运维对照应加域名例外还是 CIDR。

### 与既有 change 的关系

- 本变更修订 `webhook-private-deployment-whitelist` 所确立的「域名匹配即放行 / 官方域名内置种子」等出站语义；该 change 引入的可配置域名字段与 CIDR 表予以保留，但域名语义按上文收窄。

## Testing Decisions

好的测试只断言外部行为（给定 URL + 白名单夹具 → 接受 / 拒绝及错误码），不绑定私有辅助函数名或缓存内部结构。

优先 seam：

1. `SSRFValidator.validate`（及现有 `apps/core` 下 SSRF 测试作为 prior art）：覆盖公网域名放行、内网域名无例外拒绝、域名白名单全等后内网多 IP 放行、硬黑名单不可被域名 / CIDR 覆盖、纯 IP 无白名单拒绝、纯公网 IP 有 CIDR 放行、字面量变形按纯 IP 处理。
2. Webhook 发送 / 「测试」路径：断言改为依赖统一校验后的接受与 `NETWORK_WHITELIST_REQUIRED` 契约；可用夹具替换白名单读取与 DNS（`getaddrinfo`），prior art 见既有 webhook validation 测试。
3. 网络白名单序列化：CIDR 仍拒超网；域名字符约束与全等规范化；不再要求「内置四域名必须存在」类断言，改为断言内置种子移除后的行为。
4. 明确不回归收紧：`validate_llm_endpoint`、`validate_callback` 既有用例保持通过。

DNS 与多 IP 场景在测试中用 `getaddrinfo` mock 固定返回值，避免依赖真实解析。

## Out of Scope

- 修改 `validate_llm_endpoint` 或 `validate_callback` 的宽松策略。
- 除 `*.example.com` 前缀通配外的其它通配语法（如 `**.x`、中间 `*`、正则）。
- 按租户或按通道隔离的白名单作用域。
- 存量纯 IP 配置的自动发现、回填迁移或功能开关双轨。
- 将 DNS 解析结果钉死在通道创建时以对抗 rebinding（仍为每次校验 / 发送时解析）。
- 全站所有非 `validate` 出站路径的逐一审计与改造（本变更以统一 `validate` 与 Webhook 接入为界）。
- 前端「一键把失败 IP 加入白名单」类辅助流程。

## Further Notes

- 「域名不拦截」在共识中的准确含义是：不再用域名字符串作为公网放行条件，也不是对域名跳过解析；域名必须解析，再按 IP 黑名单 + 两类例外（CIDR / 域名全等）判定。
- 纯 IP 一律要 CIDR（含公网纯 IP）是相对当前 `validate` 对公网字面量默认放行的收紧；已接受硬切换成本，发布说明需点名。
- 私有化企微主路径：管理员添加一条域名白名单即可，无需枚举全部内网 A 记录；若 webhook 写成纯 IP，则走纯 IP 必白名单规则。
