# QUALITY_SCORE.md

> 「什么算合格」的客观标尺。提交前对照本表;红线项不达标 = 不可合并。

## 1. 最小门禁(按改动模块,提交前必跑)

| 改动落在 | 命令 |
|----------|------|
| `server/` | `cd server && make test`(`pytest` 退出码 0) |
| `web/` | `cd web && pnpm lint && pnpm type-check` |
| `mobile/` | `cd mobile && pnpm lint && pnpm type-check` |
| `agents/stargazer/` | `cd agents/stargazer && make lint`(pre-commit) |
| `webchat/` | `cd webchat && npm run build && npm run test` |
| `algorithms/<svc>` | `cd algorithms/<svc> && uv run pytest` |

> **覆盖率门槛**:改动代码覆盖率 **≥75%**(`pytest --cov`)。可在 `server/pytest.ini` 加 `--cov-fail-under=75` 强制,但须先确认存量达标,避免存量不足拖红全部提交(TODO:确认现状后落地)。

## 2. 自动门禁(已落地,别绕过)

- `.husky/pre-commit`:对 `web/`、`mobile/` staged 变更自动 lint/type-check。
- `server/.pre-commit-config.yaml`:`black` + `isort` + `flake8` + `check_migrate` + `check_requirements`。
- Python 行宽 **150**,日志用 `loguru`。

## 3. 代码质量红线(硬性)

- [ ] TypeScript:接口用 `interface`,**禁用 `any`**,不可信输入用 `unknown`
- [ ] Python:black + isort + flake8 全过,行宽 ≤150
- [ ] **无空 `except`**
- [ ] **日志无敏感信息**
- [ ] FalkorDB 语法(CMDB),**无 Neo4j 语法**
- [ ] **禁用原生 SQL**:走 Django ORM,无 raw SQL / `.raw()` / `RawSQL` / `cursor.execute`(跨 `DB_ENGINE` 方言)
- [ ] **下发不伤宿主**:插件/作业下发不致目标主机崩溃、死机、数据丢失;不可逆操作有边界与确认
- [ ] 新增依赖**附理由**
- [ ] 只改必要文件,**无顺手重构 / 全仓格式化**

## 4. 测试质量(server)

- **TDD**:新功能/bugfix 先按 **红-绿-重构** 推进(先写失败测试,通常从 `_pure`/`_service` 起步)。
- **有效性**:测**行为/契约**而非实现细节;**禁止凑覆盖率的无效测试**(无断言、断言常量、镜像实现、永真)。
- **覆盖率**:改动代码 **≥75%**;关键/安全路径(鉴权、下发、事务、金额/权限)必须覆盖。
- 遵循 `server/docs/testing-guide.md`(分层、BDD、中文 Gherkin)。
- 文件名后缀分层:`_pure`(无 DB/IO)/ `_service`(mock 依赖)/ `_views`(DRF via `api_client`)。
- Marker:`unit` / `integration` / `bdd` / `slow`;`asyncio_mode = auto`。
- 全局 fixture:`authenticated_user` / `api_client` / `request_factory`(`server/conftest.py`)。
- bugfix 必须**带回归测试**(参见近期 `e4dee9ba6`:修复合并错误 + 补 3 条单测)。

## 5. 评分速查(自评,合并前)

| 维度 | 不合格(0) | 合格(1) |
|------|-----------|---------|
| 门禁 | 未跑/有红 | 对应模块命令退出码 0 |
| 红线 | 触犯任一硬性红线 | 全清 |
| 测试 | 改行为无新测试 / 无效凑数测试 | 先写测试、测行为、改动覆盖率 ≥75% |
| 范围 | 夹带无关改动 | 最小 diff |
| 验证 | 「应该没问题」 | 有命令/输出证据 |

5 项全 1 才算「完成」。详见 [core-beliefs §7 改完必验](docs/design-docs/core-beliefs.md)。
