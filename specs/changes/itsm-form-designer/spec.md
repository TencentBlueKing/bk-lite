# ITSM 表单设计

Status: ready

## Problem Statement

表单设计人把控件拖进画布时，字段经常不落在指针处，单选和多选默认占满一行，分组也不能当容器。预览又带着设计器说明，看不出提单人实际会填什么。

## Solution

画布按指针插入字段，分组只做一层容器。单选和多选默认半行，整行字段保持整行。画布和预览都显示真实控件，预览页只留下表单本身。

## User Stories

1. As a 流程设计人, I want to drag a field onto the canvas and see an insertion bar between rows or beside a field, so that the field lands where I pointed and the row widths rebalance.
2. As a 流程设计人, I want 单选 and 多选 to start at half a row, and 分组、表格、富文本这类整行字段保持整行, so that the default layout matches the field type.
3. As a 流程设计人, I want to drop fields into a 分组 and be stopped from nesting a 分组 inside a 分组, so that the group stays a single container.
4. As a 流程设计人, I want the form canvas to keep scrolling while I drag, so that a long form stays reachable.
5. As a 流程设计人, I want each field to preview as its real control, and the preview page to show only the form, so that I am not reading designer labels instead of the form.
6. As a 提单人, I want required fields inside a 分组, option checks, and numeric bounds to be enforced even when a bound was stored as text, so that an invalid form cannot be submitted.

## Implementation Decisions

- 表单插入只看指针。两行之间插入新行，并给新字段和下一字段换行。同一行字段左右插入后重排宽度：1 或 2 个为一半，3 个为三分之一，4 个为四分之一，一行最多 4 个。整行类型不并入已有行。
- 分组不能包含分组。
- 单选、多选默认一半行宽。整行类型包括分组、子表单、嵌套表格、任务、标签页、富文本、子流程表单、CAB、多选配置项。
- 左侧控件用小图标，按基础、高级、场景三组着色。画布和预览渲染真实控件，不展示标识、类型标签和宽度徽章。预览页不展示说明标题和字段计数。
- 表单校验覆盖分组内字段。数字上下限先转成数字再比较。单选、下拉、级联以及复选、多选下拉、多选级联都检查选项是否存在。
- 计算公式只允许 sum、avg、concat、now、if。
- 拖拽继续使用现有拖拽库，不引入另一套表单设计器。

## Testing Decisions

- 只看校验错误和清理后的表单值。
- 用现有表单校验测试锁住：字符串形式的数字边界、分组内必填、复选和多选的非法选项、隐藏字段跳过、只读字段不写回。

## Out of Scope

- 把计算公式扩展到任意四则运算。
- 替换当前表单画布。
- 流程节点、工单动作和资源列表。

## Further Notes

- 表单设计同时出现在流程设计器的表单页签和独立表单设计页，两边共用同一套画布规则。
