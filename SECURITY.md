# SECURITY.md

> BK-Lite 安全基线与威胁约定。原则见 [core-beliefs §6](docs/design-docs/core-beliefs.md);本文是可执行的「红线 + 检查清单」。

## 1. 密钥与配置(强制红线)

- 仅以 `*.example` / `*.template` 提供样例,**真实密钥永不入库**。
- `.env`、`*.keystore`、`keystore.properties` 为敏感文件,已在 `.gitignore` / `mobile/.gitignore` 排除,不得绕过。
- 所有凭据(DB / NATS / JWT / Redis / NPM_TOKEN / MinIO)经**部署环境注入**,不写入代码、不写入日志。
- 新增 env 走 `os.getenv` 默认值,**不改 `server/envs/.env.example`**(该文件易冲突,见团队约定)。

## 2. 认证与会话

- 自定义用户模型 `base.User`,多后端(Session / API Secret / 标准)。
- Web → 后端经 `/api/proxy/core/api/login/`,统一由 `_set_auth_cookie_on_response()` 设置 `bklite_token` cookie(登录入口必须复用此辅助函数,见 [AGENTS.md](AGENTS.md) 与 `server/apps/core/views.py`)。
- `bk_lite_login` 是内部函数,**不暴露为 URL 路由**。
- 认证源 / SSO 经 NATS 接入,接口规范见 [docs/readme.md](docs/readme.md)。

## 3. 编码红线

- 禁止空 `except` 块(吞异常 = 吞安全事件)。
- 禁止在日志记录密码、token、cookie、个人敏感信息。
- TypeScript 禁用 `any`,用 `unknown` 收敛不可信输入,降低注入面。
- CMDB 图查询用 FalkorDB 语法,**禁止 Neo4j 语法**(误用语法可能导致注入/越权查询)。
- 权限校验不可被参数旁路 —— 历史上 `node_list` 出现过 `skip_permission` 旁路缺陷(见 `memory/project_issue_3125_fix.md`),涉及列表/详情接口须确认权限链未被跳过。

## 4. 提交前安全自检

- [ ] 没有新增明文密钥 / token / 内网地址
- [ ] 没有新增空 `except`
- [ ] 日志无敏感字段
- [ ] 新权限接口的权限链已覆盖(无 skip 旁路)
- [ ] 改动若触及上传/反序列化/外部命令,已确认输入来源可信

## 5. 自动化安全审计

仓库已落地安全审计循环(见 `memory/project_security_audit_loop.md` 与根目录 `security_audit_loop.md`):私密优先、全栈目标、产出完整 Patch,并用 `fp-check` 反假阳。发现高置信漏洞 → 走该流程,不在普通 PR 里夹带。

## 6. 上报路径

- 代码层疑似漏洞:走安全审计循环 + `fp-check` 验证后立项修复。
- 配置/部署层:经部署环境处置,不在仓库内 hotfix 密钥。

> TODO: 补充依赖供应链审计节奏(确认位置:`server/pyproject.toml`、`web/package.json`、`supply-chain-risk-auditor` skill)。
