# 编排中心 MVP：预发真实验证（先验证，再按证据修复）

Status: in-progress（本地栈 A 组 9/9 live 通过；B/C 以契约单测抽证，C3 四类触发实跑未全闭环）  
Date: 2026-10-13

## 目标

在**本机可运行栈**上完成独立试用所需的真实验证（预发暂不可用时的替代环境）；修复清单由实跑证据驱动，不以单测替代主路径/硬风险验收。

环境假设与进程缺口见 [ENV_INVENTORY.md](./ENV_INVENTORY.md)。

## 非目标

- 不在缺少预发证据时凭想象开一批功能改造
- 不把 TDD/BDD 结果标成「独立试用已验收」
- 本变更不包含无关部署文件（`compose.yaml`、ansible-executor 本地配置等）

## 已落地（代码侧，待预发证实）

- Archify F1–F6：执行身份、OpenAPI Operate、敏感封存、版本 digest、UNKNOWN/作业 checkpoint、claim 围栏
- 终止流程联动取消关联 Job（`termination_job_cancels`）

## 本轮交付物

1. [GRILL_DECISIONS.md](./GRILL_DECISIONS.md) — 下一轮工作方式共识  
2. [validation.md](./validation.md) — 预发检查清单与结果表（由操作者填写）

## 完成定义

- A 组（主路径含终止→Job）全部有预发「通过」证据  
- B/C 组：能实跑的通过或失败已修复；仅外部阻塞可标「未实验」，且不计入独立试用已验收  
- 本轮已定位且环境内可修的缺陷全部清掉

## 本轮已修（本地证据）

- 独立文档验收样例补齐 `data.host`；作业失败 `data=null` 时文档原子补空结构
- 通知验收选用 email 渠道（跳过告警中心 NATS）并探测 SMTP；本地 Mailpit `:1025`
- `UNKNOWN` 纳入软删未终态集合；MVP 状态契约同步

## 下一步

- C3 补齐 CRON/WEBHOOK/NATS 各一次实跑闭环（若环境具备）
- 预发对照仍未做；提交 F1–F6/终止→Job 等代码变更待操作者明确要求时再 commit
