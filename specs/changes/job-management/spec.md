# Job Management

Status: draft

## Migration Context

- Legacy source: `openspec/changes/job-management/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

BK-Lite 当前缺乏统一的作业管理能力，无法对远程主机执行脚本、分发文件、运行 Playbook 等运维操作。运维人员需要依赖外部工具或手动登录执行，效率低且无审计追踪。需要构建完整的作业管理模块，支持多种执行方式、定时调度、执行记录追踪及安全防护。

## What Changes

- 新增作业管理后端模块 `apps/job_mgmt/`，包含脚本库、Playbook 库、目标管理、作业执行、定时任务、安全规则等完整功能
- 新增作业管理前端页面 `web/src/app/job-mgmt/`，包含首页、快速执行、文件分发、定时任务、作业记录、模板库、目标管理、系统配置等页面
- 集成现有 CMDB 主机数据作为执行目标来源
- 集成 Celery + django-celery-beat 实现异步执行和定时调度
- 支持 nats-executor / SSH / Ansible 多种执行驱动

## Capabilities

### New Capabilities

- `script-library`: 脚本库管理，支持 Shell/Python/Bat/Powershell 脚本的 CRUD、参数定义、组织归属
- `playbook-library`: Playbook 库管理，支持 ZIP 上传、版本控制、入口文件配置、README 展示
- `target-management`: 目标管理，支持执行目标的 CRUD、驱动配置（nats-executor/SSH/Ansible）、凭据关联
- `job-execution`: 作业执行核心，包含快速执行脚本/Playbook、文件分发、执行状态追踪、主机级日志
- `scheduled-task`: 定时任务管理，支持简单周期和 Cron 表达式、并发策略、启用/禁用
- `job-history`: 作业记录查询，支持多维度筛选、分页、执行详情查看
- `dangerous-rules`: 高危命令/路径规则管理，支持正则/通配符匹配、拦截策略、系统级与租户级规则

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

### 后端
- 新增 Django App: `server/apps/job_mgmt/`
- 新增数据模型: Script, Playbook, Target, JobExecution, JobExecutionHost, PlaybookStepExecution, FileDistributionItem, ScheduledTask, DangerousCommandRule, DangerousPathRule
- 新增 Celery Tasks: 脚本执行、文件分发、Playbook 执行、定时任务触发
- 新增 API ViewSets: ScriptViewSet, PlaybookViewSet, TargetViewSet, JobExecutionViewSet, ScheduledTaskViewSet, DangerousRuleViewSet
- 依赖: Celery, django-celery-beat, paramiko (SSH), ansible-runner (Ansible)

### 前端
- 新增页面模块: `web/src/app/job-mgmt/`
- 新增页面: 首页、脚本库、Playbook库、快速执行、文件分发、定时任务、作业记录、作业详情、目标管理、高危命令配置、高危路径配置
- 复用组件: CustomTable, OperateModal, PermissionWrapper, Tag

### 集成
- CMDB: 读取 Instance/Node 作为可选目标来源
- Node Management: 复用 nats-executor 执行通道
- 权限系统: 新增作业管理相关权限点

### 数据库
- 新增 10+ 数据表
- 新增数据库迁移文件

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-03-03
```
