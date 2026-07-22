# 2026 04 15 Fix Redis Tool Editor Ui

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-15-fix-redis-tool-editor-ui/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

Redis Tool Editor 编辑弹窗存在三个交互缺陷：

1. `OperateModal` 未设置 `width`，使用 Ant Design 默认 520px，而 `RedisToolEditor` 左侧列表固定 `w-[260px]`，导致右侧表单区域仅剩约 220px，字段过于拥挤、难以操作。
2. `handleAddRedisInstance` 在 `setRedisInstances` 的 state updater 回调内部调用 `setSelectedRedisInstanceId`，触发时 instances 状态尚未更新，`RedisToolEditor` 找不到对应 ID，右侧表单渲染为空白。
3. 新增实例后列表不会自动滚动到底部，用户需要手动向下滚动才能看到刚添加的条目。

## What Changes

- 为编辑 Redis 工具的 `OperateModal` 设置合适的宽度，使左侧列表与右侧表单都有充足空间。
- 将 `setSelectedRedisInstanceId` 调用从 `setRedisInstances` updater 内部移至外部，确保新实例被添加到状态后才设置选中 ID，消除空白渲染问题。
- 在 `RedisToolEditor` 左侧列表中增加自动滚动逻辑，新增实例后自动定位到最后一个条目。

## Capabilities

### New Capabilities

### Modified Capabilities
- `redis-tool-editor-interaction`: 修复 Redis Tool Editor 编辑弹窗的宽度、新增空白与自动滚动交互缺陷。

## Impact

## Implementation Decisions

## Context

`RedisToolEditor` 是一个左右分栏布局的组件：左侧为固定宽度 `w-[260px]` 的实例列表，右侧为 `flex-1` 的配置表单。该组件被包裹在 `OperateModal` 中展示。当前 `OperateModal` 没有传入 `width`，使用 Ant Design 默认 520px，导致右侧空间严重不足。

新增实例的逻辑位于 `toolSelector.tsx` 的 `handleAddRedisInstance`，当前在 `setRedisInstances` updater 内部调用 `setSelectedRedisInstanceId`，违反 React state updater 应为纯函数的原则，并导致选中 ID 在 instances 更新前已被设置，右侧表单找不到对应实例而显示空状态。

## Goals / Non-Goals

**Goals:**
- 弹窗宽度足以容纳左右分栏布局，右侧表单字段有正常的可用空间。
- 点击"添加"后右侧立即展示新实例的配置表单，不出现空白。
- 新增实例后，左侧列表自动滚动到最后一个条目可见。

**Non-Goals:**
- 不改动 Redis Tool Editor 的功能逻辑或表单字段。
- 不修改 `OperateModal` 的全局默认宽度，仅在 Redis 编辑场景透传宽度。
- 不引入新的动画或过渡效果。

## Decisions

### 1. 将 `width={800}` 通过 `OperateModal` props 传入

`OperateModal` 已通过 `...modalProps` 将所有额外 props 透传给 Ant Design `Modal`，因此只需在 `toolSelector.tsx` 中对 Redis 编辑弹窗加 `width={800}`，不需要改动 `OperateModal` 组件本身。

选择原因：最小改动，不影响其他使用 `OperateModal` 的场景。800px 在左侧 260px + padding 后，右侧约 480px，满足表单展示需求。

### 2. 将 `setSelectedRedisInstanceId` 移出 state updater

在 `handleAddRedisInstance` 中，先用当前 `redisInstances` 计算新实例，再分别调用 `setRedisInstances` 和 `setSelectedRedisInstanceId`，React 会在同一批次内应用两次状态更新，确保渲染时两个状态同步。

```ts
// Before (buggy)
const handleAddRedisInstance = () => {
  setRedisInstances((prev) => {
    const nextInstance = getDefaultRedisInstance(getNextRedisInstanceName(prev));
    setSelectedRedisInstanceId(nextInstance.id); // ❌ side effect in updater
    return [...prev, nextInstance];
  });
};

// After (correct)
const handleAddRedisInstance = () => {
  const nextInstance = getDefaultRedisInstance(getNextRedisInstanceName(redisInstances));
  setRedisInstances((prev) => [...prev, nextInstance]);
  setSelectedRedisInstanceId(nextInstance.id);
};
```

### 3. 在 `RedisToolEditor` 列表容器上挂载 `useRef`，通过 `useEffect` 在 instances 长度变化时滚动到底部

`redisToolEditor.tsx` 接受 `instances` 作为 prop，当 `instances.length` 增大时，说明刚刚新增了条目，此时对列表容器调用 `scrollTop = scrollHeight` 即可滚到底部。

```ts
const listRef = useRef<HTMLDivElement>(null);
const prevLengthRef = useRef(instances.length);

useEffect(() => {
  if (instances.length > prevLengthRef.current && listRef.current) {
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }
  prevLengthRef.current = instances.length;
}, [instances.length]);
```

挂载到现有的 `overflow-y-auto` 列表 div 上，不新增任何 DOM 元素。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-15
```

## Work Checklist

## 1. 修复弹窗宽度

- [x] 1.1 在 `web/src/app/opspilot/components/skill/toolSelector.tsx` 中，找到 Redis 编辑场景使用的 `OperateModal`，为其添加 `width={800}` prop。

## 2. 修复新增后空白问题

- [x] 2.1 在 `toolSelector.tsx` 的 `handleAddRedisInstance` 中，将新实例的创建移出 `setRedisInstances` updater，分别独立调用 `setRedisInstances` 与 `setSelectedRedisInstanceId`。

## 3. 新增后自动滚动到最后一个条目

- [x] 3.1 在 `web/src/app/opspilot/components/skill/redisToolEditor.tsx` 中，为左侧列表的 `overflow-y-auto` div 添加 `ref`，并通过 `useEffect` 监听 `instances.length` 变化，在长度增大时将 `scrollTop` 设为 `scrollHeight`。

## 4. 验证

- [x] 4.1 执行 `cd web && pnpm type-check` 确认无类型错误。
