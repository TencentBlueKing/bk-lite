# PLANS.md

> 「现在在做什么 / 接下来做什么」的索引。**计划与规格的真相源是 [openspec/](openspec/),不在本文复制** —— 本文是导航视图。

## 1. 规格与变更引擎:OpenSpec

本项目已采用 OpenSpec 工作流,**新需求/变更走它**,不要另起炉灶:

| 内容 | 位置 |
|------|------|
| 已确立的规格(42 个) | [openspec/specs/](openspec/specs/) |
| 进行中 / 已完成的变更 | [openspec/changes/](openspec/changes/) |
| 历史存档 | [.openspec/archive/](.openspec/archive/) |
| 工作流技能 | `.agents/skills/openspec-*`、`.opencode/command/opsx-*` |

常用入口(Skill):`opsx:new`(立项)→ `opsx:propose` / `opsx:ff`(出 artifacts)→ `opsx:apply`(实现)→ `opsx:verify` → `opsx:archive`。

## 2. 已落地能力归档:superpowers

已实现能力的计划 + 规格(各 17 / 31 篇)在 [docs/superpowers/](docs/superpowers/)(`plans/` 与 `specs/`),作为「做过什么」的参考库。

## 3. 技术债

技术债逐条追踪由团队按内部约定维护;发现新债及时登记、写明「确认位置(路径+关键词)」,不散落在代码注释。

## 4. 与目标文档模板的对齐说明

本项目的「active/completed 执行计划」由 `openspec/changes/`(进行中)与 `docs/superpowers/`(已完成)承担。仅当某计划不适合 OpenSpec 流程时,才在 `docs/exec-plans/active/` 临时落一份 markdown,完成后移入 `completed/`。

> 单一真相源原则见 [core-beliefs §5](docs/design-docs/core-beliefs.md)。
