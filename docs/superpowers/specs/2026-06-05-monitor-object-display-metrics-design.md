# Monitor Object Display Metrics Design

## Context

The current prototype at `spec/prototype/监控系统/集成/对象.html` manages monitor object types and objects. The object table already has an operation column with edit/delete actions for custom objects and a shared modal style for object configuration.

This change adds a display metrics configuration entry before the existing edit action. The configuration defines which metrics appear as columns in object view lists for a main object and, when present, its child objects.

## Goals

- Add a `展示` action for every object, including built-in and custom objects.
- Place `展示` before `编辑` in the object table operation column.
- Open a display metrics configuration modal from the `展示` action.
- Support configuring display columns for the main object and each child object.
- Support multiple template metric mappings under one display column.
- Support ordering display columns.

## Non-Goals

- Do not add enable/disable controls for display columns.
- Do not configure column width, unit, threshold color, or other presentation details.
- Do not persist data beyond the static prototype behavior.
- Do not implement real template/object validation.
- Do not update the view page to render the configured columns.

## Recommended Approach

Use a modal with an optional object tree and display-column cards.

When the selected object has child objects, the modal body is split into two areas:

- Left object tree: main object first, followed by child objects.
- Right configuration area: display columns for the currently selected object.

When the selected object has no child objects, the object tree is hidden and the configuration area fills the modal body.

This keeps the configuration direct for simple objects while still making multi-object cases, such as `Kubernetes / Pod / Node`, easy to understand.

## Entry Point

In the object table operation column:

- Built-in objects show `展示`.
- Custom objects show `展示 / 编辑 / 删除`.
- The `展示` button opens the display metrics configuration modal.

The modal title should include the object name, for example:

```text
展示指标配置 - 主机
展示指标配置 - Kubernetes
```

## Modal Layout

The display modal should be wider than the existing create/edit object modal because it contains list configuration.

With child objects:

```text
展示指标配置 - Kubernetes

[ Kubernetes ]   展示列配置
[ Pod        ]   + 添加展示列
[ Node       ]   ----------------
                 CPU使用率
                   模版A / CPU使用率
                   模版B / cpu_usage
```

Without child objects:

```text
展示指标配置 - 主机

展示列配置
+ 添加展示列
----------------
CPU使用率
  模版A / CPU使用率
  模版B / cpu_usage
```

## Display Column Card

Each display column card represents one column in the view list.

Each card contains:

- Drag handle for ordering display columns.
- Column name input, such as `CPU使用率`.
- Template metric mapping rows.
- `添加指标` action for adding another mapping under the column.
- Delete action for removing the display column.

Example:

```text
CPU使用率
  模版A / CPU使用率
  模版B / cpu_usage

内存使用率
  模版A / 内存使用率
  模版C / mem_used_percent
```

This means the view list has one `CPU使用率` column, but its value can come from different metrics depending on the template used by each object instance.

## Template Metric Mapping

Each mapping row contains:

- `采集模板` select.
- `指标` select.
- Remove action for deleting the mapping row.

The metric select is conceptually dependent on the selected template. In the prototype, static sample options are enough to demonstrate the interaction.

Sample template options:

- `模版A`: `CPU使用率`, `内存使用率`, `磁盘使用率`
- `模版B`: `cpu_usage`, `mem_usage`, `disk_usage`
- `K8s模版`: `pod_cpu_usage`, `pod_memory_usage`, `node_cpu_usage`

Multiple mapping rows are allowed under the same display column.

## Interactions

- Click `展示` to open the modal.
- If child objects exist, click the left object tree to switch between main object and child objects.
- Click `添加展示列` to add a display column card.
- Click a display column delete action to remove that column.
- Click `添加指标` inside a card to add a template metric mapping row.
- Click a mapping row remove action to delete that mapping.
- Drag display column cards to reorder display columns.
- Click `确定` to close the modal.
- Click `取消` or close icon to close without additional behavior in the prototype.

## Data Shape for Prototype

The prototype can keep static display configuration data in the page script. A shape like this is sufficient:

```js
displayMetricConfigs = {
  host: {
    host: [
      {
        name: 'CPU使用率',
        mappings: [
          { template: '模版A', metric: 'CPU使用率' },
          { template: '模版B', metric: 'cpu_usage' },
        ],
      },
    ],
  },
  kubernetes: {
    kubernetes: [...],
    pod: [...],
    node: [...],
  },
};
```

The first nested key represents the configured object or child object id. This supports main object and child object configurations without introducing real persistence.

## Testing

Because this is a static prototype change, verification should focus on manual browser behavior:

- All object rows show `展示`.
- Built-in object rows still do not show `编辑` or `删除`.
- Custom object rows show `展示 / 编辑 / 删除`.
- `展示` opens the modal with the correct object name.
- Objects without child objects do not show the object tree.
- Objects with child objects show the object tree and can switch configuration panels.
- Columns can be added, removed, and reordered.
- Metric mappings can be added and removed.
- The modal closes from `取消`, `确定`, and the close icon.
