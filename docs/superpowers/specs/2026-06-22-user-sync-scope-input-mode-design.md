# 系统管理用户同步范围输入模式设计

> 说明：本文档记录系统管理处“用户同步拉取范围输入方式”设计，仅覆盖集成实例 `user_sync` 能力的范围配置，不包含企业微信私域地址、登录认证或其他集成中心议题。

## 背景

当前系统管理的用户同步配置已经接入 provider manifest 驱动能力：

- 前端通过 provider `business_template` 渲染 `user_sync` 配置表单
- 后端通过 provider `adapter` 执行 `list_departments`、`sync_users`
- `business_config.root_department_id` 作为同步范围的核心配置值贯穿保存、预览和正式同步

但当前实现对 `root_department_id` 有固定假设：

- 前端固定将 `root_department_id` 渲染为部门树选择器
- 后端固定通过 `list_departments` 返回值校验 `root_department_id` 合法性

这使当前实现仅适合“可枚举部门树”的 provider，例如飞书；对于 AD 一类“拉取范围是 DN/OU 字符串”的 provider，例如 `ou=paas,dc=bktest,dc=com`，现状无法支持手工输入范围。

## 目标

1. 保持现有 `user_sync` 配置仍以 provider manifest 为中心，不引入新的页面特判体系
2. 支持 provider 根据自身要求动态展示：
   - 部门树选择框
   - 手工范围输入框
3. 保持 `business_config.root_department_id` 作为统一范围字段，不拆分成多套配置键
4. 对飞书等现有部门树 provider 保持兼容，不改变现有保存、预览、同步路径
5. 为 AD 等 provider 提供手工输入范围的最小接入路径

## 非目标

- 不在本次设计中处理企业微信私域地址
- 不重做集成中心 provider 框架
- 不引入全新的远端资源选择器框架
- 不在第一阶段引入复杂的 AD DN 语法解析器
- 不改造 `user_sync` 之外的 `login_auth`、`im_notification` 能力

## 现状

当前关键实现位于：

- 前端
  - `web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx`
  - `web/src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx`
  - `web/src/app/system-manager/utils/userSyncUtils.ts`
- 后端
  - `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
  - `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
  - `server/apps/system_mgmt/services/user_sync_service.py`
  - `server/apps/system_mgmt/providers/adapters/base.py`
  - `server/apps/system_mgmt/providers/adapters/feishu.py`

当前行为为：

1. `root_department_id` 在前端被固定渲染为 `TreeSelect`
2. 页面通过 `department_options` 接口调用 `list_departments`
3. 创建页切换实例时，默认写入 `root_department_id="__all__"`
4. serializer 在保存时强制调用 `list_departments` 校验所选范围是否合法
5. `sync_users` 最终消费 `business_config.root_department_id`

因此现状的问题不是单纯前端控件类型问题，而是“前端渲染 + 后端校验”都绑定在“部门树可枚举”模型上。

## 设计原则

### 1. 范围输入方式属于字段自身元数据

“这个范围字段是选择还是手输”应归属于 `root_department_id` 字段本身，而不是页面级硬编码分支。新 provider 应只通过 manifest 声明行为，不要求前端新增 provider 特判。

### 2. 统一配置键，分离输入方式

无论 provider 采用部门树还是手输范围，最终仍统一写入 `business_config.root_department_id`。输入方式变化不应导致配置模型分裂。

### 3. 前后端按同一模式决策

前端渲染方式与后端校验方式必须来自同一份 manifest 元数据，避免出现“页面可填但保存失败”或“页面限制与后端校验不一致”的情况。

### 4. 兼容现有 provider，默认保守

未声明新元数据的旧 provider 默认按现有 `department_select` 语义处理，避免飞书等已接入能力被破坏。

## 推荐方案

采用“字段级范围输入模式”方案。

在 `user_sync` 对应 `business_template` 中，为 `root_department_id` 字段增加扩展元数据：

- `input_mode: "department_select" | "manual_input"`

语义定义：

- `department_select`
  - 表示该 provider 支持列举范围选项
  - 前端展示部门树选择器
  - 后端通过 `list_departments` 校验
- `manual_input`
  - 表示该 provider 需要用户手工输入范围
  - 前端展示普通文本输入框
  - 后端不再依赖 `list_departments` 校验

## 方案对比

### 方案 A：字段级 `input_mode`，推荐

- 优点
  - 保持 provider manifest 驱动模型完整
  - 新 provider 接入只需声明模式并实现自身 adapter
  - 前后端都可复用统一配置键
- 缺点
  - 需要扩展模板字段 schema
  - 需要前后端同步识别新元数据

### 方案 B：前端按 provider_key 特判

- 优点
  - 开发速度快
- 缺点
  - 页面逻辑会持续膨胀
  - 后端仍然需要补同等规模特判
  - 长期难维护

### 方案 C：重构成通用资源选择框架

- 优点
  - 长期抽象更完整
- 缺点
  - 明显超出当前需求
  - 投入与风险不成比例

结论：采用方案 A。

## 详细设计

### 一、数据模型

扩展 provider manifest 的字段元数据模型，使 `TemplateFieldManifest` 支持附加输入模式信息。

建议新增字段：

- `input_mode`
  - 取值：`department_select`、`manual_input`
  - 默认值：空；运行时按 `department_select` 兼容处理

对于 `user_sync` 业务模板：

- 飞书 provider 的 `root_department_id` 声明 `input_mode=department_select`
- AD provider 的 `root_department_id` 声明 `input_mode=manual_input`
- `manual_input` provider 不应在同一模板中声明 `department_id_type` 字段；该字段仅属于部门树模式

最终数据存储不变，仍保存在：

- `business_config.root_department_id`

### 二、前端渲染

前端重点改造 `UserSyncConfigFields.tsx`。

当前逻辑是：

- 只要 `field.key === "root_department_id"`，就固定渲染为 `TreeSelect`

目标逻辑是：

1. 读取 `root_department_id` 字段的 `input_mode`
2. 根据模式选择控件：
   - `department_select` -> `TreeSelect`
   - `manual_input` -> `Input` 或 `TextArea`

具体要求：

- `department_select`
  - 保持当前部门树加载逻辑
  - 保持加载失败、失效选择等提示
  - 继续使用 `department_options`
- `manual_input`
  - 不请求 `department_options`
  - 不展示部门树相关提示
  - 继续复用字段原生 `placeholder` 和 `help_text`
  - 表单校验仅保留必填与通用字符串校验

同步调整点：

- `UserSyncOperateModal.tsx`
  - 当前在切换实例时默认写入 `root_department_id="__all__"`
  - 调整为仅 `department_select` 模式下才写入该默认值
- `userSyncUtils.ts`
  - `getDefaultDepartmentIdType()` 仅在 `department_select` 模式下生效
  - `manual_input` 模式不自动注入 `department_id_type`
  - 当 provider 为 `manual_input` 时，前端忽略历史残留的 `department_id_type` 值，不参与提交构造

### 三、后端校验

后端重点改造 `UserSyncSourceSerializer.validate()`。

当前逻辑：

- 固定要求 `root_department_id` 存在
- 固定调用 `list_departments`
- 固定校验 `root_department_id` 必须存在于部门树返回值中

目标逻辑：

1. 根据 `integration_instance.provider_key` 找到 provider manifest
2. 定位 `user_sync` 对应 `business_template`
3. 读取 `root_department_id.input_mode`
4. 按模式决定校验方式

校验规则：

- `department_select`
  - 保持现有逻辑
  - 调用 `list_departments`
  - 做 `__all__` 归一化
  - 校验选中值必须在合法范围内
- `manual_input`
  - 校验 `root_department_id` 非空
  - 不调用 `list_departments`
  - 保存前忽略 `department_id_type` 等部门树模式遗留字段
  - 原样保留输入值写入 `business_config`

默认兼容策略：

- 当 manifest 未声明 `input_mode` 时，后端按 `department_select` 处理
- 当 provider 声明 `manual_input` 时，serializer 应主动剔除或忽略传入的 `department_id_type`

### 四、provider 与 adapter 职责

provider 的职责：

- 通过 manifest 声明 `root_department_id` 的输入方式
- 通过 adapter 消费 `business_config.root_department_id`

adapter 的职责：

- `department_select` provider
  - 实现 `list_departments`
  - `sync_users` 继续使用选择结果作为范围
- `manual_input` provider
  - 可不依赖 `list_departments`
  - `sync_users` 直接将 `root_department_id` 作为范围参数使用

说明：

- 不应依赖 `BaseUserSyncAdapter.list_departments()` 的默认“全部部门”虚拟节点来兼容 `manual_input`
- 因为当前问题不在“有没有默认返回值”，而在“是否应调用部门树校验”

### 五、AD 接入方式

本设计下，AD provider 的最小接入路径为：

1. 在 `user_sync` 的 `business_template` 中声明：
   - `root_department_id.input_mode = manual_input`
2. 在前端显示普通范围输入框
3. 在保存时后端仅做非空校验
4. 在 `sync_users` 中将 `business_config.root_department_id` 直接作为 AD 查询范围

这允许用户输入：

- `ou=paas,dc=bktest,dc=com`

而不需要平台先具备“枚举 AD OU 树”的能力。

### 六、历史数据兼容

本次改造默认不支持“同一个已上线 provider 从部门树模式切换为手工输入模式”的在线平滑迁移。

兼容约束如下：

- 已存在的飞书等 `department_select` provider 保持原模式，不变更为 `manual_input`
- `manual_input` 主要面向新接入 provider，例如 AD
- 若未来确实需要将既有 provider 从 `department_select` 切换为 `manual_input`，必须单独设计迁移方案，不纳入本次改造范围

原因：

- 已保存的 `root_department_id` 可能是 `__all__`、真实部门 ID 或历史部门树节点值
- 这些值对 `manual_input` provider 没有通用可解释语义
- 若直接透传到新 adapter，预览和正式同步可能误将历史树模式值当作原始范围字符串使用

因此本次实现采用保守策略：

- 不做自动迁移
- 不承诺跨模式复用旧数据
- 仅保证新增 `manual_input` provider 的数据模型与运行时链路成立

## 错误处理

### `department_select`

- 保持当前策略
- 部门加载失败时前端展示错误提示
- 已选部门失效时提示重新选择
- 保存时后端返回“所选范围无效”

### `manual_input`

- 第一阶段仅处理非空错误
- 若后续需要更严格规则，可在第二阶段增加：
  - manifest 声明正则 pattern
  - provider 自定义 `validate_scope`
  - serializer 调用 provider 级格式校验

本次设计不强制第一阶段实现 AD DN 语法校验，以降低落地复杂度。

### `department_options` 运行时行为

`department_options` 是公开运行时接口，本次需要明确其在 `manual_input` provider 下的合同：

- 前端不应主动请求 `manual_input` provider 的 `department_options`
- 后端收到这类请求时，应直接返回 `400`
- 返回信息应明确指出当前 provider 的范围输入模式不支持部门树选项加载

这样可以避免未来出现：

- 页面误调用后端接口却收到貌似可用的默认树数据
- 测试或外部调用方误以为 `manual_input` provider 仍支持部门树模式

## 测试策略

### 1. 飞书回归

- 创建用户同步源仍显示部门树
- 切换实例后仍可默认选择全部部门
- `department_options` 仍会按 `department_id_type` 刷新
- 无效部门值仍会被拒绝

### 2. `manual_input` 新模式

- 创建页展示输入框而不是部门树
- 不再请求 `department_options`
- 手工调用 `department_options` 时后端返回 `400`
- 可以输入 `ou=paas,dc=bktest,dc=com`
- 保存、预览、正式同步均可透传该值

### 3. 模式切换

- 从 `department_select` 切到 `manual_input` 时不残留 `__all__`
- 从 `manual_input` 切回 `department_select` 时恢复部门树逻辑
- 编辑已有 source 时回填值与控件类型一致

### 4. 兼容性

- 未声明 `input_mode` 的旧 provider 继续按部门树模式工作
- `manual_input` provider 的模板中不再声明 `department_id_type`
- serializer 对 `manual_input` 输入主动忽略遗留的 `department_id_type`

## 风险与缓解

### 风险 1：前端默认值污染

当前创建页默认写入 `root_department_id="__all__"`，若未按模式隔离，可能污染 `manual_input` provider 的真实输入。

缓解：

- 仅在 `department_select` 模式下注入该默认值

### 风险 2：后端仍隐式依赖部门树校验

若 preview、save 或 update 路径中仍保留固定 `list_departments` 依赖，会出现“页面能输入、保存时报错”。

缓解：

- 将校验入口统一收敛到 serializer 的模式分支

### 风险 3：字段 schema 前后端不同步

如果前端识别了 `input_mode` 但后端未识别，或反之，会造成行为不一致。

缓解：

- 同步扩展前后端字段 schema
- 为 `input_mode` 默认值补兼容测试

### 风险 4：既有 provider 被误改成 `manual_input`

如果后续把已有 `department_select` provider 直接改成 `manual_input`，历史保存值可能无法被新语义正确解释。

缓解：

- 将该场景明确视为单独迁移项目
- 本次范围内仅支持新增 `manual_input` provider，不支持既有 provider 在线切换语义

## 实施建议

按以下顺序落地：

1. 扩展 provider manifest 字段 schema，支持 `input_mode`
2. 前端将 `root_department_id` 渲染逻辑改为按模式分支
3. 后端 serializer 将范围校验改为按模式分支
4. 为飞书补回归测试
5. 为 `manual_input` 模式补新增测试

## 结论

推荐以 `root_department_id` 字段级 `input_mode` 为核心，将“部门选择”和“手工范围输入”统一纳入现有 provider manifest 体系：

- 前端按模式渲染
- 后端按模式校验
- provider 只声明模式并消费统一范围值

该方案可以在不推翻现有架构的前提下，为飞书等部门树 provider 保持兼容，同时为 AD 等手工范围 provider 提供清晰、低风险的接入路径。
