# Codex Delegation Review 提示词模板(严格 Review + TDD 修复 + 收口)

> 这是一份给 Codex 子任务 / delegation 线程使用的提示词模板。
> 目标是把「review」「讨论提示词」「确认后修复」三类任务拆清楚，避免子线程拿到上下文后直接跑偏到写代码。
> 基于 BK-Lite CMDB 一周提交 review 实战总结，可直接复用或按需删减。

---

## 一、Codex Delegation 总入口(必须放在提示词最前)

```xml
<codex_delegation>
  <source_thread_id>上一会话或主线程 ID</source_thread_id>
  <mode>review_only | discuss_prompt | fix_confirmed</mode>
  <target_branch>feature_windyzhao</target_branch>
  <worktree_policy>使用目标分支的独立 worktree；若当前是 Codex detached worktree，先说明状态，不要擅自创建/切换。</worktree_policy>
  <scope>server/apps/cmdb/ 或具体文件/目录</scope>
  <do_not_modify>true</do_not_modify>
  <input>
    这里放具体 review / 讨论 / 修复要求。
  </input>
</codex_delegation>
```

### mode 语义

| mode | 允许动作 | 禁止动作 |
|------|----------|----------|
| `review_only` | 读代码、跑只读命令、输出 review 结论 | 修改代码、写测试、修复、提交 |
| `discuss_prompt` | 讨论/修改提示词、文档模板 | 修改业务代码、跑业务测试、进入修复流程 |
| `fix_confirmed` | 按已确认问题做 $diagnosing-bugs + TDD 修复 | 未确认根因前改实现、顺手修无关历史失败 |

### 强制纠偏规则

- 如果用户说「错了」「不是这个」「用这个提示词讨论」，立即停止当前方向。
- 先汇报当前未提交改动文件；等用户确认后只回滚自己造成的改动。
- 不继续执行原 delegation 任务，不把旧任务当作默认上下文。
- 如果 `mode=review_only` 或 `do_not_modify=true`，即使发现 P0 也只输出结论，不写测试、不改实现。

---

## 二、Review 入口提示词(Codex delegation 版)

```text
/review @<scope> 帮我严格 review 这段改动，要技术严谨、不要客套。

Codex delegation 参数：
- mode: review_only
- target_branch: <branch>
- worktree: <path 或「当前 Codex worktree」>
- scope: @server/apps/<app>/
- do_not_modify: true

review 对象与背景：
@server/apps/<app>/ 帮我检查最近一周的代码提交质量，有无代码编写错误，写法是否不规范。
请 review 后端代码，重点关注 bug 风险、行为回归、Django ORM 使用、测试覆盖、权限/安全边界，
以及是否符合仓库 AGENTS.md 的后端规范。请按严重程度列出问题，并给出文件和行号。

若未指定对象，默认 review 当前分支相对 master 的 diff。

执行要求：
1. 必须先遵守 AGENTS.md，读取 `CONTEXT.md`、相关 capability/change spec 与目标代码。
2. 使用 `$code-review` 视角，分两轮过：
   - 第一轮【正确性】：bug、边界条件、空值/异常处理、并发与事务、安全(注入/越权/敏感信息)、与原有逻辑兼容。
   - 第二轮【质量】：重复代码可否复用、是否能更简化、有无明显低效、命名与抽象层次是否得当。
3. 每条问题给出：文件:行号 + 为什么是问题 + 具体怎么改。
4. 报告前做「反驳验证」：拿不准、可能误报的，要么继续核实，要么标注「待确认」，不要堆似是而非的发现。
5. 按严重度分层：必须修(P0) / 建议改(P1) / 可选(P2-P3)。如果某块代码没问题，直接说没问题，不硬凑。
6. 只输出 review 结论，先不要动代码；等我确认要修哪些，再进入 fix_confirmed。
```

---

## 三、修复入口提示词(Codex delegation 版)

```text
/fix 按照 P0 到 P3 的顺序进行修复。

Codex delegation 参数：
- mode: fix_confirmed
- target_branch: <branch>
- worktree: <独立 worktree path>
- scope: <已确认要修的问题列表>
- do_not_modify: false

缺陷信息：
<粘贴已确认的 review 结论，保留文件:行号、严重度、期望行为。>

请这样走：
1. 先用 $diagnosing-bugs。没完成根因调查，不准改任何代码。
   - 先确认能否稳定复现、读全报错；
   - 多组件系统要在每个组件边界看数据流，先定位哪一层断了；
   - 给出一个有证据支撑的单一根因假设，不列一堆可能修法。
2. 根因确认后停下来等我确认；确认后再用 test-driven-development：
   - 先写失败测试；
   - 亲眼看它失败，且失败原因是目标 bug，不是环境或 typo；
   - 再写最小修复转绿。
3. 一次只修一个根因，不顺手重构无关代码，不盲目修所有历史失败。
4. 修完排查同根因是否在多条路径重复存在。
5. 宣称修好前必须用 verification-before-completion：
   - 跑聚焦测试；
   - 能做 Red-Green 双向验证时，临时恢复 bug 写法确认测试会 FAIL，再恢复修复确认 PASS；
   - 输出真实测试命令、退出码和关键结果。
6. 收口用 finishing-a-development-branch；合并到目标分支时优先 cherry-pick 我的提交，不整分支 merge。

本仓库专属约定：
- 跑单测优先使用仓库记录的命令；无测试库环境时走 mock-ORM + conda env。
- 后端 bugfix 必须 TDD；新测试测行为，不测实现。
- 禁止原生 SQL / .raw() / RawSQL / cursor.execute。
- 最小 diff，只改确认范围内文件。
- 不提交，除非用户明确要求。
```

---

## 四、提示词讨论 / 模板修改入口

```text
请只讨论或修改这个提示词模板，让它更适合 Codex delegation 使用。

Codex delegation 参数：
- mode: discuss_prompt
- scope: docs/reviews/<template>.md
- do_not_modify_business_code: true

要求：
1. 不进入业务代码 review 或修复。
2. 可以读取模板文件和相关仓库规范。
3. 修改前先说明改造方案；用户确认后再改文档。
4. 若误改业务代码，立即报告 dirty 文件并按用户要求回滚。
```

---

## 五、流程骨架(可复用)

```text
review_only
  -> 加载 AGENTS/仓库事实源
  -> 确认 worktree/branch/scope
  -> 两轮 review(正确性 + 质量)
  -> 反驳验证
  -> 严重度分层输出
  -> 等用户确认

fix_confirmed
  -> 加载 AGENTS/仓库事实源
  -> $diagnosing-bugs 根因调查
  -> 根因确认点：停下来等用户确认
  -> TDD 失败测试
  -> 最小修复
  -> Red-Green 双向验证
  -> 聚焦/必要全量测试
  -> 收口，等用户确认是否提交/PR/cherry-pick

discuss_prompt
  -> 读取模板
  -> 提出改造方案
  -> 用户确认
  -> 修改文档
  -> 读回验证
```

---

## 六、严重度分层标准

| 层级 | 含义 | 例子 |
|------|------|------|
| P0 必须修 | 会出 bug / 安全 / 回归 | 行为回归、空值崩、注入、越权、缺事务、敏感信息泄露 |
| P1 建议改 | 质量 / 重复 / 抽象 / 契约不清 | 命名误导、权限收口不完整、黑名单覆盖不全 |
| P2-P3 可选 | 效率 / 风格 / 重构 / 文档 | 重复逻辑、性能损耗、文档陈旧、字符串拼接风格 |

---

## 七、Review 输出格式

```text
结论：发现 <N> 个问题，其中 P0 <n> 个，P1 <n> 个，P2-P3 <n> 个。

P0 必须修
1. <文件:行号> <标题>
   - 为什么是问题：...
   - 反驳验证：已核实 <证据> / 待确认 <缺口>
   - 建议修法：...

P1 建议改
...

P2-P3 可选
...

无问题区域
- <文件/模块>：已检查，未发现需要提出的问题。

测试/验证说明
- 本次是 review_only，未修改代码。
- 已运行/未运行的只读验证命令：...
```

---

## 八、TDD 验证模板

```bash
# 1. 写失败测试
uv run pytest apps/<app>/tests/test_<file>.py -k "<new_test>" -q --no-cov
# 预期：1 failed，且失败原因是目标 bug

# 2. 应用最小修复
# 只改根因相关 src/test 文件

# 3. 复测 PASS
uv run pytest apps/<app>/tests/test_<file>.py -k "<new_test>" -q --no-cov
# 预期：1 passed

# 4. Red-Green 双向验证
# 临时恢复 bug 写法或用最小反向 patch 确认测试 FAIL，再恢复修复确认 PASS

# 5. 全量/聚焦回归
uv run pytest apps/<app>/tests/<所有 touched test files>.py -q --no-cov
```

---

## 九、中断与纠偏模板

当用户中断并指出方向错误时，Codex 必须输出：

```text
收到，我停止当前方向。

已产生的未提交改动：
- <file1>
- <file2>

我将按你的新指令处理：<新任务摘要>。
是否回滚上述改动？
```

如果用户明确说「回滚」，只回滚自己造成的文件，不使用 `git reset --hard`，不碰用户已有改动。

---

## 十、收口提示词

```text
实现完成。当前未提交改动 <N> 个文件，base 是 <base-branch>。

测试结果：
- uv run pytest <聚焦测试> -> <结果>
- uv run pytest <必要回归> -> <结果>
- Red-Green 双向验证：<已做/未做及原因>

未解决/非本次范围：
- <已知历史失败或待确认项>

4 个选项：
1. 提交当前修复
2. 推送并开 PR
3. 保持当前 worktree，不提交
4. 丢弃本次改动，需二次确认

请选。
```

---

## 十一、常见陷阱 Checklist

- [ ] delegation mode 没写清，导致 Codex 从 review 跑到修复
- [ ] 用户要求讨论提示词，却误改业务代码
- [ ] review_only 下写了测试或实现
- [ ] 未做反驳验证，输出似是而非的发现
- [ ] 多个修复一起上，无法定位回归来源
- [ ] 测试因为环境/typo 失败，却当成红灯
- [ ] 修完没有 Red-Green 双向验证
- [ ] 合并时整分支 merge，带入无关冲突
- [ ] 中断后没有汇报 dirty 文件

---

## 十二、与仓库工具的衔接

- AGENTS.md / CLAUDE.md：任何 review/fix 都必须遵守仓库入口规则。
- 仓库事实源：共享术语读 `CONTEXT.md`，长期约束读 `specs/capabilities/`，跨会话变更读 `specs/changes/`。
- 调用链：使用 `rg`、源码和测试证据还原，不依赖仓库专用索引服务。
- 测试命令：`cd server && uv run pytest apps/<app>/tests/<file>.py -q --no-cov`；特殊环境按仓库 runbook 记录执行。
