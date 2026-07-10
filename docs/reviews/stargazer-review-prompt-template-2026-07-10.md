# Stargazer Delegation Review 提示词模板(严格 Review + TDD 修复 + 收口)

> 这是一份给 Codex 子任务 / delegation 线程使用的 Stargazer 专用提示词模板。
> 目标是把 `agents/stargazer/` 的 review、提示词讨论、确认后修复拆清楚，避免子线程把 Agent 框架误按 Django/CMDB 后端规则处理。
> 可参考 CMDB review 模板的流程骨架，但审查模型必须按 Stargazer 的插件执行、任务队列、NATS 回调、远程执行和资源边界重新展开。

---

## 一、Codex Delegation 总入口

```xml
<codex_delegation>
  <source_thread_id>上一会话或主线程 ID</source_thread_id>
  <mode>review_only | discuss_prompt | fix_confirmed</mode>
  <target_branch>feature_windyzhao</target_branch>
  <worktree_policy>使用目标分支的独立 worktree；若当前是 Codex detached worktree，先说明状态，不要擅自创建/切换。</worktree_policy>
  <scope>agents/stargazer/ 或具体文件/目录</scope>
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
| `fix_confirmed` | 按已确认问题做 systematic-debugging + TDD 修复 | 未确认根因前改实现、顺手修无关历史失败 |

### 强制纠偏规则

- 如果用户说「错了」「不是这个」「用这个提示词讨论」，立即停止当前方向。
- 先汇报当前未提交改动文件；等用户确认后只回滚自己造成的改动。
- 不继续执行原 delegation 任务，不把旧任务当作默认上下文。
- 如果 `mode=review_only` 或 `do_not_modify=true`，即使发现 P0 也只输出结论，不写测试、不改实现。

---

## 二、Stargazer Review 入口提示词

```text
/review @<scope> 帮我严格 review Stargazer 这段改动，要技术严谨、不要客套。

Codex delegation 参数：
- mode: review_only
- target_branch: <branch>
- worktree: <path 或「当前 Codex worktree」>
- scope: @agents/stargazer/ 或具体文件/目录
- do_not_modify: true

review 对象与背景：
@agents/stargazer/ 帮我检查指定范围的代码提交质量，有无代码编写错误，写法是否不规范。
请按 Stargazer Agent 框架审查，重点关注插件执行链路、任务队列、NATS 回调、本地/远程执行安全、
敏感信息日志、资源边界、插件契约、测试覆盖，以及是否符合仓库 AGENTS.md 的 Agent 规则。
请按严重程度列出问题，并给出文件和行号。

若未指定对象，默认 review 当前分支相对 master 的 diff。

执行要求：
1. 必须先遵守 AGENTS.md / projectmem：调用 get_instructions、get_summary、get_project_map；涉及具体文件时 precheck_file。
2. 有 `.codegraph/` 时优先用 CodeGraph 理解执行链路；无索引时说明并改用 `rg`。
3. 使用 requesting-code-review 视角，分两轮过：
   - 第一轮【正确性】：bug、边界条件、空值/异常处理、异步并发、队列去重、回调一致性、安全(命令注入/任意文件读取/敏感信息)、与原有逻辑兼容。
   - 第二轮【质量】：重复代码可否复用、是否能更简化、有无明显低效、命名与抽象层次是否得当、插件契约是否清晰。
4. 每条问题给出：文件:行号 + 为什么是问题 + 具体怎么改。
5. 报告前做「反驳验证」：拿不准、可能误报的，要么继续核实，要么标注「待确认」，不要堆似是而非的发现。
6. 按严重度分层：必须修(P0) / 建议改(P1) / 可选(P2-P3)。如果某块代码没问题，直接说没问题，不硬凑。
7. 只输出 review 结论，先不要动代码；等我确认要修哪些，再进入 fix_confirmed。
```

### 配置采集推荐首批 scope

```text
agents/stargazer/api/collect.py
agents/stargazer/core/task_queue.py
agents/stargazer/tasks/handlers/plugin_handler.py
agents/stargazer/service/collection_service.py
agents/stargazer/core/plugin_executor.py
agents/stargazer/tasks/utils/nats_helper.py
agents/stargazer/plugins/inputs/network_config_file/
agents/stargazer/plugins/inputs/config_file/
agents/stargazer/tests/test_network_config_file_info.py
agents/stargazer/tests/test_api_http_layer.py
```

---

## 三、Stargazer 修复入口提示词

```text
/fix 按照 P0 到 P3 的顺序修复已确认的 Stargazer 问题。

Codex delegation 参数：
- mode: fix_confirmed
- target_branch: <branch>
- worktree: <独立 worktree path>
- scope: <已确认要修的问题列表>
- do_not_modify: false

缺陷信息：
<粘贴已确认的 review 结论，保留文件:行号、严重度、期望行为。>

请这样走：
1. 先用 systematic-debugging。没完成根因调查，不准改任何代码。
   - 先确认能否稳定复现、读全报错；
   - 多组件链路要在每个边界看数据流，例如 API 参数 -> Redis 队列 -> Worker -> PluginExecutor -> 插件 -> NATS 回调；
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

Stargazer 专属约定：
- 修插件优先写 `agents/stargazer/tests/` 下聚焦单测，mock NATS/Redis/Netmiko/SSH，不依赖真实设备。
- 涉及远程执行、主机文件读取、网络设备命令执行时，必须有资源边界、超时、幂等/可回滚语义和错误回调。
- 配置内容、`content_base64`、密码、secret、设备原始输出不得完整进入日志。
- 最小 diff，只改确认范围内文件。
- 不提交，除非用户明确要求。
```

---

## 四、流程骨架

```text
review_only
  -> 加载 AGENTS/projectmem
  -> 确认 worktree/branch/scope
  -> 用 CodeGraph/rg 还原 Stargazer 执行链路
  -> 两轮 review(正确性 + 质量)
  -> 反驳验证
  -> 严重度分层输出
  -> 等用户确认

fix_confirmed
  -> 加载 AGENTS/projectmem
  -> precheck_file
  -> systematic-debugging 根因调查
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

## 五、严重度分层标准

| 层级 | 含义 | Stargazer 例子 |
|------|------|----------------|
| P0 必须修 | 会出 bug / 安全 / 回归 / 资源耗尽 | 敏感配置写日志、任意文件读取无边界、危险命令可执行、大网段一次性全量扫描、callback 丢失导致任务永久挂起 |
| P1 建议改 | 质量 / 重复 / 抽象 / 契约不清 | 插件返回结构不一致、错误分类误冷却凭据、黑名单覆盖不全、任务 TTL 与真实等待窗口不匹配 |
| P2-P3 可选 | 效率 / 风格 / 重构 / 文档 | 重复 helper、命名误导、日志字段不统一、测试 fixture 可读性差 |

---

## 六、Stargazer Review Checklist

### 执行链路

- [ ] `api/collect.py` 是否正确解析 headers/query/body，是否避免把凭据或大字段写日志。
- [ ] `core/task_queue.py` 的 task_id、dedupe_key、running_key 是否覆盖 host、credential、collect_task_id、config_file_path 等必要维度。
- [ ] ARQ/Redis TTL 是否覆盖真实任务执行、callback 等待和失败清理窗口。
- [ ] `tasks/handlers/plugin_handler.py` 的成功/失败路径是否都能发布 metrics 或 callback。
- [ ] `service/collection_service.py` 是否区分 callback 模式和 Prometheus metrics 模式，失败结构是否一致。
- [ ] `core/plugin_executor.py` 动态 import 和 enterprise/oss fallback 是否有明确边界。

### 插件与回调契约

- [ ] `plugin.yml` 的 module/class/script 路径是否与文件结构一致。
- [ ] 插件 `list_all_resources()` 是否稳定返回 `{"success": bool, "result": ...}`。
- [ ] callback payload 是否包含 `collect_task_id`、`instance_id`、`instance_name`、`model_id`、`file_path`、`file_name`、`status`、`size`、`error`。
- [ ] callback 失败路径是否和成功路径身份字段一致。
- [ ] `content_base64` 是否只在成功且必要时返回，不在日志、错误和指标里扩散。

### 执行安全

- [ ] 网络设备命令是否有允许/拒绝策略，能拦截写入、重启、跳转 shell、远程复制、SSH/Telnet 等危险命令。
- [ ] 脚本渲染是否正确转义用户输入，避免 shell/PowerShell 注入。
- [ ] 主机配置文件读取是否限制文件类型、大小和输出体积。
- [ ] 本地执行与 SSH 执行是否有明确超时、错误分类和不可逆操作边界。
- [ ] 远程回调或 NATS subject 是否不能由不可信参数任意拼接到高权限主题。

### 资源边界

- [ ] 大网段/IP 范围是否有数量上限和并发上限。
- [ ] 大文件/超长命令输出是否有大小上限和截断策略。
- [ ] 一次性 `gather`、全量列表、整文件读入内存是否可能耗尽 agent 资源。
- [ ] timeout、conn_timeout、execute_timeout、worker job_timeout 是否语义一致。

### 多凭据与冷却

- [ ] credential/unreachable/task/SNMP timeout 分类是否准确。
- [ ] 单凭据与多凭据的冷却行为是否符合预期，避免误伤临时抖动。
- [ ] 成功凭据缓存、失败状态清理和下一凭据入队是否不会重复/漏跑。

### 测试

- [ ] 单测优先 mock NATS/Redis/Netmiko/SSH/文件系统边界。
- [ ] 新测试测行为，不测私有实现细节。
- [ ] review_only 不写测试；fix_confirmed 必须先写失败测试。

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
cd agents/stargazer
uv run pytest tests/test_<target>.py -k "<new_test>" -q
# 预期：1 failed，且失败原因是目标 bug

# 2. 应用最小修复
# 只改根因相关 src/test 文件

# 3. 复测 PASS
uv run pytest tests/test_<target>.py -k "<new_test>" -q
# 预期：1 passed

# 4. Red-Green 双向验证
# 临时恢复 bug 写法或用最小反向 patch 确认测试 FAIL，再恢复修复确认 PASS

# 5. 聚焦/必要回归
uv run pytest tests/test_<target>.py tests/test_<related>.py -q
make lint
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
- make lint -> <结果>
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

- [ ] delegation mode 没写清，导致 Codex 从 review 跑到修复。
- [ ] 用户要求讨论提示词，却误改业务代码。
- [ ] 把 Stargazer 当 Django app 审，输出 ORM/ViewSet/事务类误报。
- [ ] review_only 下写了测试或实现。
- [ ] 未做反驳验证，输出似是而非的发现。
- [ ] 只看插件文件，漏掉 API -> 队列 -> Worker -> 回调的跨层契约。
- [ ] 测试因为环境/typo 失败，却当成红灯。
- [ ] 修完没有 Red-Green 双向验证。
- [ ] 合并时整分支 merge，带入无关冲突。
- [ ] 中断后没有汇报 dirty 文件。

---

## 十二、与仓库工具的衔接

- AGENTS.md / CLAUDE.md：任何 review/fix 都必须遵守仓库入口规则。
- projectmem：会话开始调用 get_instructions、get_summary、get_project_map；修改文件前 precheck_file；发现/尝试/修复按 log_issue / record_attempt / record_fix 记录。
- CodeGraph：有 `.codegraph/` 时 review 阶段优先 `codegraph_explore`；无索引时说明并改用 `rg`。
- Stargazer 测试：`cd agents/stargazer && uv run pytest tests/<file>.py -q`；门禁按仓库约定运行 `make lint`。
