# 系统管理 · 凭据仓库产品决策记忆

- 最近更新：2026-09-07
- 当前规格：`docs/superpowers/plans/2026-09-03-system-mgmt-credential-vault.md`

## 产品定位

系统管理提供凭据**实例仓库**和给其它模块用的选用组件 / NATS。口令存一次，消费方按 `credential_id` 引用。扫描 / 监控 / 作业接线不在本需求。

## 已确认范围

- 仓库：类型目录 + 实例 CRUD、停用、轮换。
- 公共组件：下拉选用 + 快捷新建；权限收在组件内。
- HTTP（页面/组件）+ NATS（`list_credentials` / `create_credential` / `resolve_credential`）。
- `resolve_credential` 由本团队提供，仅服务端调用，明文不回页面。

## 已确认设计决策

- 对外身份是 `credential_id`，形态 `crd-{type_key}-{uuid4 去横线 32 位}`，系统生成、不可改；不用数据库自增 ID。
- 两表：`CredentialType`、`Credential`。不建 Category 表、不建引用账本。
- `categories` 为字符串列表，不定死枚举。
- 消费查询：`category` + `type` 双重过滤。
- **组织**：分台账和消费两套。消费（`selectable` / NATS `list_credentials` / `resolve_credential` / 公共组件选项）：**归属向下共享**，`group_id ∈ {current_team} ∪ 活动祖先`，且当前组织在授权内；父组织选不到子组织名下的凭据。台账（系统管理列表、创建/编辑所属组织、停用/删除）：**编辑者授权组织**（登录 `group_list` 的活动组织；超管为全部活动组织），不再按当前节点裁子孙。公共组件快捷新建只挂**当前组织**。归档组织不参与祖先链。角色点仍按稿：管台账 View/Add/Edit/Delete；引用不占「使用」、不要求凭据 Edit。
- 下拉再加未停用。
- 引用列按真实引用展示，**禁止写死 0**。计数问询与拦截规则见「跨模块契约」：无数据源显示「—」；删除、改组织在询问失败时按仍有引用处理。
- 公共组件：`+ 新增凭据` 看 Add（无权限置灰 + API 403）；`系统管理 ↗` 看 View（无权限不渲染）。`permissionPath` 指向凭据菜单路由。
- 仓库新建/编辑/查看用 `ContentFormDrawer`；快捷新建和类型元数据用 `OperateModal`；类型字段设计用宽抽屉，左侧字段列保持原型，右侧预览共用动态表单。
- **内置字段展示名**：`name` 用中文（原型 `label`）；`id` 仍为英文 token。类型抽屉标题中文、芯片英文；创建凭据表单和预览用 `name`。分类仍双语。英文界面字段名后置。SNMP「用户名 (Security Name)」、云 AK/SK 等无通行中文的术语按原型保留括注。
- **枚举选项**：契约仍是 `values` 为不重复字符串数组，值即实例取值、显示条件比较值和消费 token；添加字段弹窗维持逗号分隔输入。不引入中文名称/英文 token 两列，也不抄监控「添加指标」的原始值/映射值/颜色。监控表单只作后续行编辑结构参考。
- 列表：名称/ID 双行；类型只 Tag；分类列（类型 Tab）双行中文+英文。名称旁无锁图标。

## 跨模块契约

系统管理负责仓库本身，以及给其它模块用的无密文列表和按 `credential_id` 解析明文（NATS `list_credentials` / `create_credential` / `resolve_credential`）。

**引用计数 RPC（系统管理定契约，消费方实现）：** 不建引用账本。仓库列表、删除、改组织时，系统管理把本页/当前条的一批 `credential_id` 拿去问消费方。载荷形状统一；方法名按模块前缀，避免共用 NATS namespace 撞名。本期只问 CMDB、监控，作业等以后用同一载荷另加方法。

系统管理用通用 `RpcClient().run` **直接请求**下列方法名，不经 `apps/rpc/cmdb.py`、`apps/rpc/monitor.py`，也不经 `apps/rpc/system_mgmt.py`（后者只封装别人问仓库的 `list`/`create`/`resolve`）。

方法：

- CMDB：`cmdb_count_credential_refs`
- 监控：`monitor_count_credential_refs`

入参：

```json
{ "credential_ids": ["crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"] }
```

- `credential_ids` 为去重后的字符串数组，单次不超过仓库列表页上限（100）。空数组返回空 `counts`。
- 不要求 `actor_context`：计数的是该 ID 在消费方任务/实例上的引用条数，不是当前组织可见条数。

出参：

```json
{ "result": true, "data": { "counts": { "crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 2 } } }
```

- `counts` 的 key 必须是入参里的 ID；未引用的 ID 显式为 `0`，不得省略后让调用方猜。
- `result: false` 与超时、无订阅者一样视为询问失败。

展示与拦截：

- 列表芯片：CMDB / 监控各自成功返回的数字按模块加总（如「CMDB 2」「监控 1」）。两家都失败或都未接线 → 无数据源，显示「—」，禁止写死 0。
- 一家成功一家失败：只展示成功那家的芯片；失败那家在删除/改组织时按仍有引用处理。
- 删除、改组织：任一家失败、超时或返回 `count > 0` → 拦截。两家都成功且该 ID 合计为 0 才放行。
- 列表询问建议短超时（数秒），避免拖垮仓库页；删除/改组织同样短超时，超时当仍有引用。

系统管理不负责 CMDB/监控任务加列、表单改选仓库、执行或测试连接去 resolve，也不负责他们内部怎么数。他们未实现 handler 时，系统管理可以定向尝试调用，失败按上款处理。

消费查询必须 `category` + `type`。明文不回页面。

**页面引用：** 业务任务/实例原表单要选仓库凭据时，在现有 `Form` 里加 `Form.Item`，子组件用 `web/src/components/credential-picker` 的 `CredentialPicker`。`name` 存 `credential_id`；用 `category` + `type` 锁范围。列表由组件自己请求系统管理，业务页不要再拉一遍、不要自绘下拉。编辑回填把已有 `credential_id` 放进表单 `initialValues` / `setFieldsValue` 即可。口令不进业务表；执行侧明文走服务端 `resolve_credential`。不要用 Storybook 里的 `CredentialPickerChrome`（那是纯 UI 预览）。

## 明确后置

- 扫描 / 监控 / 作业改任务表、落 ID、执行调用、字段映射。
- CMDB / 监控实现 `cmdb_count_credential_refs` / `monitor_count_credential_refs`；系统管理按契约定向询问并画芯片。作业等计数口后置。
- 仓库侧连通测试、条级授权、另存为、外部 Vault、从 UI.json 发明类型。
- 有引用后禁删 / 禁改组织（等对接方落 ID，超时仍按有引用处理）。
- 枚举选项改成监控那种一行一项加减，以及「显示名称 ≠ 存库 token」的值/名称分离；待自定义类型确实需要再改 schema 与 picker。

## 仍待确认

- 无。

## 已替代决策

- 曾考虑类型内序号生成 `credential_id`；2026-09-03 改为 UUID 后缀。
- 曾写「消费方不要传 category」；已纠正为类型过滤必须 `category` + `type`。
- 曾写「一期引用列固定显示 0」；2026-09-03 改为：不做对接则无数据源、列为空，不是假的 0。
- 曾写可见性 =（当前 ∪ 子孙）∩ 授权（父列表扫子孙名下凭据）；2026-09-03 改为：归属向下共享。
- `凭据.md` 的「同组织」不按字面实现；2026-09-03 改为归属向下共享，避免外部不可变组织树导致子组织选不到上级凭据。不把「改回严格同组织」记为后置。
- 曾写创建可选归属 = 授权 ∩（当前 ∪ 活动子孙）；2026-09-07 改为：台账列表/创建/编辑用编辑者授权组织；消费选项与 resolve 仍为当前 ∪ 祖先；快捷新建只挂当前组织。

## 决策来源

- 2026-09-03：凭据.md + 凭据仓库.html 原型，及本会话对齐。组织口径以本文件「已确认设计决策」为准。
- 2026-09-04：添加字段弹窗枚举选项：保持逗号输入与 `values: string[]`；不上中文选项+英文 token，不抄监控指标颜色；行编辑与值/名称分离后置。
- 2026-09-07：台账组织范围改为编辑者授权组织；消费侧保持向下共享。
