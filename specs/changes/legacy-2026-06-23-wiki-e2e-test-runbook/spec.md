# Historical Superpowers change: 2026-06-23-wiki-e2e-test-runbook

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-23-wiki-e2e-test-runbook.md

## 0. 架构 / 端口
- 后端 Django:`:8011`(`/api/v1/opspilot/wiki_mgmt/*`)
- 前端 Next:`:3000`(经 `/api/proxy` → `NEXTAPI_URL` → 后端)
- DB:dev 库 `bklite`(已 migrate 0059–0063)
- 对象存储:MinIO(你的 env,文件落 `munchkin-private`)
- LLM/嵌入/OCR:网关 `https://api.v36.cm/v1`(模型 130 deepseek-v4-flash1 / text-embedding-3-small / gpt-4o)

## 1. 前置配置(关键 — 否则 AI/检索/OCR 不工作)
1. 后端 `server/.env` + `local_settings.py`(已就绪)。
2. 模型 provider:
   - **EmbedProvider#36**:把其 vendor 的 `api_base` 改为 `https://api.v36.cm/v1`(否则语义检索 502)。
   - **OCRProvider**:新建一个 vendor=该网关、model=`gpt-4o`(否则图片 OCR 不工作;pdf/docx/pptx 文本无需 OCR)。
   - 建知识库时选 `llm_model`(130)+ `embed_provider`(36)。
3. 前端 `web/.env`:`NEXTAPI_URL=http://localhost:8011`。

## 2. 启动后端(worktree 可直接跑)
```bash
cd server
make dev          # :8011
make celery       # 另开终端:异步构建 / 网页定时刷新
```
自检:`curl -H "Authorization: Bearer <token>" http://localhost:8011/api/v1/opspilot/wiki_mgmt/knowledge_base/` → 200。

## 3. 启动前端
### 方式 A — 主仓库(推荐,干净,所有页面可用)
```bash
# 在主工作树检出本分支前端(或合并到测试分支)
git checkout claude/bold-tu-40b23d
cd web && pnpm install
# web/.env: NEXTAPI_URL=http://localhost:8011
pnpm dev          # :3000
```
### 方式 B — worktree 内(需先清嵌套 node_modules 路由冲突)
```bash
cd /d/app/github/bk-lite/.claude/worktrees/kb-remove/web
mkdir -p ../_nm_holding
for d in src/app/*/node_modules; do m=$(basename $(dirname "$d")); mv "$d" "../_nm_holding/$m"; done   # 同盘 rename,秒级
npx next dev -p 3100
# —— 测完还原 ——
# for h in ../_nm_holding/*; do mv "$h" "src/app/$(basename "$h")/node_modules"; done
```
注:方式 B 会让 studio 等依赖 opspilot 专属包的页面暂不可用(wiki 页用 root 依赖,正常);wiki 测完按上面还原。

## 4. 登录
浏览器开 `http://localhost:3000`(或 :3100)→ admin 登录(`make setup-dev-user` 的 admin/password,或 Keycloak)。

## 5. 前后联动:文档上传 → 后台触发(逐步对照接口)
进 `/opspilot/wiki`:
1. **新建知识库**:填名称/简介 → 选模板 → 点 **AI 生成**(`POST .../knowledge_base/generate_purpose_schema/`,真实 LLM 出 Purpose/Schema)→ 保存(`POST .../knowledge_base/`)。
2. 进详情 → **资料工作区** → **新增资料**:
   - **文档上传**:类型选「文件」→ 选 `pdf/docx/pptx/xlsx/png/jpg` → 提交
     → **`POST /wiki_mgmt/material/`(multipart)** → 文件落 **MinIO** → 资料行出现(status=pending)。
   - 也可选「文本」「网页」。
3. 资料行点 **解析** → `POST .../material/{id}/ingest/` → 后端从 MinIO 读文件 → 解析(pdf/docx/pptx 原生文本;图片走 gpt-4o OCR)→ 生成 AI 摘要 → status=done。
4. 资料行点 **构建** → `POST .../material/{id}/build/` → 两步法(抽取要点 → 按 Schema 生成页面)→ BuildRecord + 知识页面。
5. **知识页面 Tab**:看生成页面 → 查看正文 / 版本 / **对比 diff** / 恢复。
6. **问答 Tab**:提问 → `POST .../qa/` → 真实 LLM 作答 + 引用(可追溯到页面/资料)。
7. **图谱 Tab**:G6 画布渲染节点/社区(先在页面正文加 `[[标题]]` 或共享资料以产生关系)。
8. **检查审核 Tab**:点 **扫描** → `POST .../scan/` → 列孤立/缺源 → 接受/拒绝。
9. **技能联动**(P4):技能设置页「选择 Wiki 知识库」多选保存 → 对话验证回答注入了 wiki 内容 + 引用。

## 6. 验收点(逐步对照)
| 步骤 | 看什么 |
|---|---|
| 上传 | Network 中 `POST material/` 201;MinIO 多一个对象 |
| 解析 | `ingest` 200;资料 status→done;AI 摘要列非空 |
| 构建 | `build` 200;知识页面 Tab 出现页面 |
| 问答 | `qa` 200;答案 + 引用可点回页面 |
| 图谱 | `graph_analysis` 200;画布有节点+社区着色 |

## 7. 回归
- 方式 A 下点其他 opspilot 页面(studio/skill)正常,确认删旧 KB 无副作用。
- 后端:`pytest apps/opspilot/tests/ -k "not wiki"` 通过。

## 自动化基线(可先跑)
- L1 单测:`pytest apps/opspilot/tests/wiki/ -m "not integration"` → 92 passed。
- L2 真实闭环 shell 脚本:见 PROGRESS.md / 会话记录(建库→AI→资料→构建→检索→问答→图谱,打真实服务)。
- 含真实 MinIO/上传:去掉 `-m "not integration"`(含 multipart 上传端点测试,已通过 201)。
