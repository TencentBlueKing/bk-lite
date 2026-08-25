# 运营分析统一筛选产品决策记忆

- 最近更新：2026-08-24
- 当前规格：`specs/changes/ops-analysis-string-param-multiple/spec.md`
- 前序规格（已实现，类型表达已被当前规格修正）：`specs/changes/ops-analysis-unified-filter-string-list/spec.md`

## 产品定位

运营分析是可视化与配置层。画布级对象选择（主机、机房、业务等）走统一筛选；单张卡片自己换口径走组件内切换。取数和下拉选项都下沉到数据源，运营分析不在前端拼多组件聚合。

## 已确认范围

- 列表传参保留：多选下拉把 ID 数组传给已绑定组件；空选择省略参数。
- 类型下拉不再提供「字符串列表」；字符串是否多选由参数输入配置中的 `multiple` 决定。
- 多选开关只出现在现有参数输入配置弹窗（控件为下拉/表格时）；生产入口为统一筛选字符串齿轮与组件查询参数字符串齿轮。
- 仪表盘、大屏、报表、拓扑等已有统一筛选栏的画布共用这套语义。

## 已确认设计决策

- 不新增场景控制器组件，不把 `componentSwitch` 升成全页控制器。
- 删除一等类型 `stringList`；用 `string` + `inputConfig.multiple` 表达数组 vs 标量（`multiple` 为基数合同）。绑定 id 统一 `key__string`。原因：类型下拉双轨误导，且多选本就属于下拉控件配置。
- 禁止逗号拼接 ID。
- 多选与 `componentSwitch` 互斥。
- 关多选时多值静默保留第一个。
- 旧 `stringList` / `key__stringList` 迁成 `string` + `multiple: true` / `key__string`。
- 数据源设置页参数表不增加多选入口；不另设「参数声明多选 / 筛选项再开多选」两套开关。
- Top10 换指标、3D 机房换当前机房继续用 `componentSwitch`。
- 主机查询数据源共用 `instance_ids`（迁移后为字符串 + 多选）。不做健康/异常主机数。

## 明确后置

- 拓扑单值面板补参数输入配置齿轮。
- 旧版静态筛选选项弹窗升级为完整参数输入配置。
- 筛选方案收藏、级联下拉、图表钻取。
- 跨仪表盘共享筛选状态。
- 平台级多选硬顶（`maxCount`）。
- 把 3D 机房下拉从组件内切换迁到统一筛选。

## 仍待确认

无。

## 已替代决策

- 「`stringList` 作为与 `string` 并列的一等可绑定类型，且 `string` 与 `stringList` 不能互绑」→ 由当前规格替代为统一 `string` + `multiple`。
- 评估阶段考虑过的组件内切换升全页、独立场景控制器仍未采纳。

## 决策来源

- 用户于 2026-08-21 grill 确认：删 `stringList`；多选仅在现有参数输入配置；两处生产齿轮入口；旧数据迁移；关多选取第一个。
- 对照：`stringList` + filter 保存失败、设置页类型下拉与真实多选入口错位。
- `specs/changes/ops-analysis-string-param-multiple/spec.md`
