# OpsPilot 智能体技能包参数

Status: ready

## Problem Statement

用户在智能体里挂载的技能包（典型如「AD 域管理工具集」）自带一批二进制与脚本，执行时需要域控地址、服务账号、密码、LDAPS 证书等凭据。当前有两条链路同时断裂，导致这类技能包在 OpsPilot 里无法使用。

其一，没有任何「给技能包传参」的通道。`LLMSkill.skill_params`（`server/apps/opspilot/models/model_provider_mgmt.py:252`）看似相关，但它是提示词模板变量：变量名由前端从提示词里正则扫 `{{key}}` 自动生成、输入框 `disabled` 不可手填，值最终由 `resolve_skill_params`（`server/apps/opspilot/utils/prompt_utils.py:11`）替换进 prompt。凭据若走这条路会进入模型上下文与对话历史，不可接受。技能包执行沙箱的环境变量是白名单硬编码的六项（`server/apps/opspilot/metis/llm/chain/node.py:2772`），没有留任何用户参数入口。

其二，技能包里的二进制根本进不了执行沙箱。导入阶段按字节落盘是完好的（`server/apps/opspilot/services/skill_package/importer.py:93` 用 `write_bytes`），但运行时物化到一次性沙箱这一步有三个叠加缺陷：`materialize_skill_package` 逐文件 `read_text(encoding="utf-8")`，二进制抛 `UnicodeDecodeError` 后被 `except Exception` 吞掉、只留一条 debug 日志（`server/apps/opspilot/services/skill_package/materializer.py:159`）；搬运范围写死为 `scripts` / `references` / `assets` 三个目录（同文件 `ASSET_DIRS`，以及 `server/apps/opspilot/services/skill_package/runtime.py:222`），技能包放在 `bin/` 或包根下的文件连扫都不扫；`backend.write` 落地的文件没有可执行位。

## Solution

给「智能体 × 技能包」增加一份执行期参数，与提示词模板变量 `skill_params` 完全分离、并存互不干扰。参数在服务端解密后只注入技能包的执行环境（进程环境变量为主，包目录内 0600 凭据文件为辅），不进提示词、不进模型上下文；加密项落库用现有 Fernet，读接口只回掩码，永不回显明文。

参数按技能包隔离注入：`PathRewritingBackend` 在委托 `execute` 前依据命令里命中的 `/skills/<包名>/` 判定归属，只注入该包的参数，调用后还原；判不出单一归属则一个都不注入（fail-closed）。执行输出回传给模型前对加密值做脱敏，堵住工具回显泄漏这条后门。

同时修复物化环节的三个缺陷，让技能包自带的二进制能落进沙箱被调用。执行放行机制（命令黑名单、首命令白名单、路径沙箱）一律不动。

分两个可独立交付的阶段：阶段一是参数本身（模型、接口、UI、加密、注入、脱敏），阶段二是物化三修。

## User Stories

1. As a 智能体管理员, I want 为智能体里挂载的每个技能包单独配置一组变量（自行填写变量名与值）, so that AD 这类需要凭据的技能包能拿到运行所需的参数。
2. As a 智能体管理员, I want 把变量标记为加密类型并在编辑时只看到掩码, so that 域管理员密码不会在页面、接口响应或数据库里以明文出现。
3. As a 智能体管理员, I want 证书 / 私钥这类多行凭据按技能包声明自动使用多行输入, so that PEM 内容不会因为单行输入框丢换行而无法使用。
4. As a 技能包作者, I want 在 `skill.yaml` 里声明本技能包需要哪些变量（含必填与说明）, so that 使用者打开配置界面就知道该填什么，而不用去翻 SKILL.md。
5. As a 智能体管理员, I want 必填变量没填时保存不被阻断、但运行时能明确知道该技能包不可用, so that 既能先存半成品，又不会在对话中途撞上一个看不懂的工具报错。
6. As a 智能体管理员, I want 移除技能包时被询问其凭据是删是留, so that 既不会误删还要复用的凭据，也不会在库里长期遗留无人引用的密文。
7. As a 智能体管理员, I want 同一技能包升级版本后凭据自动沿用, so that 不必因为技能包从 1.0 升到 1.1 就重填一遍域账号密码。
8. As a 智能体使用者, I want 一个技能包的凭据不被同一智能体里的其他技能包读到, so that 高权限凭据的暴露面限制在真正需要它的技能包内。
9. As a 技能包作者, I want 技能包里的二进制文件能被物化进执行沙箱并可执行, so that 不必把工具改写成纯脚本或预装进镜像。

## Implementation Decisions

### 语义与边界

- 参数是「技能包的执行期参数」，作用域为「智能体 × 技能包」，只交付给技能包执行环境，**不参与提示词渲染**。
- 不复用 `LLMSkill.skill_params`。该字段是活的提示词模板变量功能，有独立迁移 `0048_llmskill_skill_params`、独立 UI（`web/src/app/opspilot/(pages)/skill/detail/settings/page.tsx:560-637`）、两处运行时调用（`server/apps/opspilot/services/chat_service.py:538`、`server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py:233`）与掩码测试，语义与本变更相反。两套变量并存。
- 不改技能包的执行放行机制：`PathRewritingBackend` 的 `_ALLOWED_COMMANDS`、`_BLOCKED_PATTERNS`、路径沙箱一律不动。命令串里不出现 `$VAR`（`$VAR` 与 `${VAR}` 本就被黑名单拦截，见 `server/apps/opspilot/services/skill_executor/path_rewriting_backend.py:329`），由二进制自己读环境变量或凭据文件取值。

### 数据模型

- `LLMSkill` 新增 JSON 字段 `skill_package_params`，默认 `dict`。结构为 `{package_id: [{key, value, type, multiline}]}`。
- 外层 key 用 `package_id` 而非 `SkillPackage` 主键。`SkillPackage` 的唯一约束是 `("package_id", "version", "domain")`（`server/apps/opspilot/models/model_provider_mgmt.py:302`），升版本即新行新主键；用 `package_id` 才能让凭据跨版本沿用。
- 内层用列表而非字典，保住用户填写顺序、贴合前端 `Form.List`；同一包内变量重名由后端保存时校验拒绝。
- `type` 取值 `text` / `password` / `textarea`。`password` 加密落库；`textarea` 为多行明文。配置弹窗用同一套类型下拉，声明项只读。存储仍带 `multiline` 快照（`type == textarea`）。
- 变量名按环境变量规则校验 `^[A-Za-z_][A-Za-z0-9_]*$`。单包变量数上限 50，单值长度上限 64KB。
- `type == "password"` 的值用 `EncryptMixin`（`server/apps/core/mixinx.py`）Fernet 加密落库，与 `skill_params` 同一套密钥与工具，不引入新的加密实现。

### 读写与掩码

- 随智能体大表单一起提交，沿用 `skill_params` 现有掩码约定：读接口对 `password` 项回 `******`；更新时若收到 `******` 则从库中取回原密文，否则视为新明文并加密。密文不下发前端。
- 已保存的加密变量永不回显明文，不提供「查看明文」入口，修改只能整块覆盖。
- 类型从 `password` 切到 `text` 时前端必须清空值，避免 `******` 被当作明文存入（`skill_params` 已在 `page.tsx:624` 处理过同一问题）。
- 新字段需加入 `LLMViewSet.UPDATABLE_SKILL_FIELDS` 白名单，否则 F017 的 mass-assignment 防护会把它丢弃。
- 设置页右侧「测试」对话（`page.tsx:249-267` 的 `handleTest`）走同一套掩码合并，未保存的新填值在测试中即时生效，与 `skill_params` 行为一致。

### 技能包变量声明

- 技能包可在 `skill.yaml` 或 `SKILL.md` frontmatter 里声明 `variables: [{name, required, type, description}]`。`type` 取值 `text` / `password` / `textarea`，缺省 `text`。兼容旧字段 `secret: true` → `password`，`input: textarea` / `multiline: true` → `textarea`。接入既有的 `_manifest_with_storage_overlay` 覆盖链（`server/apps/opspilot/services/skill_package/runtime.py:230`），把 `variables` 加入 `_STRATEGY_FIELDS`，从而支持改磁盘文件热生效。
- 声明用于预填变量名、说明与必填标记；声明项的名称与类型在 UI 上只读、不可删除。未声明的技能包退化为纯自由填。
- 必填变量缺失：保存时只警告不阻断；运行时复用 `build_skill_package_prompt` 中「缺少依赖工具」的同一展示位（`server/apps/opspilot/services/skill_package/runtime.py:99-108`），在技能包目录条目下标注「缺少必填变量：xxx，本包不可用」，使模型不选它并直接告知用户去配置。

### 运行时注入

- 交付形式为进程环境变量（主）+ 包目录内 `.skillenv` 文件（辅，`KEY=VALUE` 逐行，权限 0600，仅在该包有变量时才落，随一次性沙箱销毁）。
- 按包隔离：`PathRewritingBackend.execute` / `aexecute` 用已有的 `extract_skill_names_from_text`（`path_rewriting_backend.py:44`）判定命令归属的技能包，委托前临时改写底层 `LocalShellBackend._env` 注入该包变量、调用后还原。已在 deepagents 0.6.12 实测可行：`LocalShellBackend.execute` 每次调用才读 `self._env` 并传给 `subprocess.run(env=...)`。
- 该注入方式要求同一 backend 实例上 `execute` 不并发，否则跨包串染。按最坏情况防：在 `PathRewritingBackend` 的 `execute` / `aexecute` 上加互斥锁串行化。
- fail-closed：命令未命中任何 `/skills/<包名>/`，或同时命中多个包，一律不注入任何变量；错误路径上给出「请用 `/skills/<包名>/` 绝对路径调用」的提示引导模型重试。
- 输出脱敏：`execute` 结果回传前，把本次注入的 `password` 类变量值在 `output` 中替换为 `***`，并记一条不含值的 warning 日志。`text` 类变量不脱敏，避免遮蔽域名、用户名等模型需要理解的信息。

### 物化修复（阶段二）

- 搬运时先试 `read_text` 走 `backend.write`，失败则 `read_bytes` 走 `backend.upload_files`。`upload_files` 是 deepagents `BackendProtocol` 的标准方法，`LocalShellBackend` 经 `FilesystemBackend` 继承实现，走同一个 `_resolve_path`，落点与 `write` 完全一致，因此不破坏物化器的后端无关性。
- 搬运范围从写死的三个目录改为整个 `extracted/`，排除 `SKILL.md` 与 `skill.yaml`（前者由 `render_skill_md` 重新渲染，后者是清单不是运行资源）。`hydrate_skill_packages` 注入 `asset_roots` 的三目录枚举同步放开。
- `upload_files` 的文件模式硬编码 `0o644`，无可执行位。对源文件本身带可执行位的，物化后补 `chmod`。
- 单个文件搬运失败不得静默：日志级别从 `debug` 提升，至少让运维能看见「哪个包的哪个文件没搬进去」。

### 前端

- 技能包卡片（`page.tsx:355-390` 的 `renderSkillPackageSelector`）新增一枚「变量 N」按钮，兼作状态显示与配置入口：数字为已配置项数，悬停显示「声明 N 项 / 已配置 M 项」；缺必填时按钮转告警色并在卡片下方多出一行明确告警。卡片高度在正常情况下不变。
- 新增变量配置弹窗：变量名（必填红色 `*`）与值、类型（`text` / `password` / `textarea`）同一行。声明项的类型只读；自定义变量可改类型。加密项复用现有 `EditablePasswordField`。弹窗确定仅暂存到表单，实际写入由页面底部「保存」触发。
- 移除技能包改为带确认框，框内显示该包已配置的变量数，由用户选择一并删除凭据还是保留。
- 权限沿用智能体的编辑权限，不新增权限点。变量变更记 `operation_log`，只记变量名不记值。

## Testing Decisions

- 好测试只断言外部行为：加密落库与掩码往返、按包隔离的注入与还原、fail-closed 的不注入、输出脱敏、必填缺失的运行时标注、二进制物化后在沙箱内字节一致、移除技能包时凭据按用户选择去留。不绑定内部 helper 的调用次数或私有函数结构。
- 优先接缝（由高到低）：`password` 项加密落库且读接口回 `******`、更新时掩码回填不丢密文；同一包内变量重名与非法变量名被拒；`PathRewritingBackend` 注入前后 `_env` 的差异与还原（含多包命中与零命中的 fail-closed 分支）；输出脱敏对 `password` 生效、对 `text` 不生效；`skill.yaml` 声明 `variables` 经 overlay 链热生效；缺必填时技能包目录文本包含不可用标注；物化器对二进制走 `upload_files` 且落盘字节与源文件一致、搬运范围覆盖 `bin/`。
- 并发这条要有针对性用例：并行发起两个分属不同技能包的 `execute`，断言各自只看到自己的变量。这是 `_env` 临时改写方案唯一的正确性风险，不能只靠加锁的代码存在来证明。
- 既有先验可平行：`server/apps/opspilot/tests/test_llm_viewset_views.py` 里 `get_skill_params` 的掩码用例与 `UPDATABLE_SKILL_FIELDS` 白名单用例；`test_skill_package_runtime.py`、`test_skill_materializer_pure.py`、`test_path_rewriting_backend_security.py` 的既有覆盖。新增用例应贴着这些接缝写，不引入浏览器 E2E。
- 验证环境必须用 `d:/app/venv/bkliteserver`（deepagents 0.6.12，与 `server/pyproject.toml:135` 一致）。

## Out of Scope

- 不改技能包执行的放行机制。命令黑名单、首命令白名单、路径沙箱一律保持现状。已知「首命令白名单只校验命令串第一个 token、`&&` 之后不校验」这一防护缺口，本变更不处理。
- 不把凭据接到平台已有的凭据 / 密钥管理能力上，本变更自建存储。
- 不支持在提示词或 SKILL.md 正文里用占位符引用这批参数。
- 不提供加密变量的明文查看入口，也不提供按权限解密查看。
- 不做变量的跨智能体共享、模板化或批量导入导出。
- 不做技能包级的「允许执行自带二进制」开关；信任边界仍是「技能包由管理员上传」。
- 不迁移或改动 `skill_params` 的现有行为。
- 不将执行沙箱替换为 NATS worker / 容器沙箱（Phase 1 方向另行处理），本变更仍在 `LocalShellBackend` 上落地。

## Further Notes

- 需求与设计经 grill-me 逐项对齐，结论：技能包参数不进 prompt、作用域「智能体 × 技能包」、env 主 + `.skillenv` 辅、按包隔离、fail-closed、`LLMSkill` 新 JSON 字段、`package_id` 做外层 key、大表单 + `******` 掩码、永不回显明文、自由填 + 可选声明、保存警告 + 运行时标注不可用、移除时询问凭据去留、`text`/`password`/`textarea`、输出脱敏、物化三修、执行机制不动。
- UI 原型见 `~/.cursor/projects/d-app-github-bk-lite/canvases/opspilot-agent-skill-package-params.canvas.tsx`，已确认。其中「变量 N」按钮合并状态与入口、缺必填时才额外占一行告警，是为了在两列网格布局下不抬高卡片。
- 已在 deepagents 0.6.12 实测确认三条前提：`upload_files` 按 `virtual_mode` 映射落到沙箱且字节一致；同一文件 `read_text` 抛 `UnicodeDecodeError`（现物化器静默跳过的确切原因）；`LocalShellBackend.execute` 每次调用读 `self._env`，故临时改写加还原可行。
- 仓库内 `server/.venv` 停留在 deepagents 0.2.5，缺 `LocalShellBackend`，在该环境下技能包沙箱会经 `try/except` 静默降级为「无技能包」。与本变更无关，但排查时容易误判，实现与验证一律使用 `d:/app/venv/bkliteserver`。
