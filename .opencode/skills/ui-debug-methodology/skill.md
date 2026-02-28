---
name: ui-debug-methodology
description: UI/前端问题调试方法论。当遇到 CSS、布局、组件行为等 UI 问题时，强制执行"先观察后动手"的调试流程，避免盲目尝试。
license: MIT
compatibility: All frontend projects
metadata:
  author: bk-lite
  version: "1.0"
  lesson_learned: "Ant Design Table 可拖拽列宽需求，因未理解机制而反复试错"
---

# UI 问题调试方法论

**核心原则：先理解机制，后动手修改。**

当 UI 行为不符合预期时，**禁止**立即修改代码。必须先完成以下调试流程。

---

## 强制流程

```
┌─────────────────────────────────────────────────────────────┐
│                    UI 问题调试流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 观察现象        用 DevTools 检查实际 DOM 和样式          │
│       │                                                     │
│       ▼                                                     │
│  2. 理解机制        搞清楚组件/CSS 的工作原理                │
│       │                                                     │
│       ▼                                                     │
│  3. 定位根因        找到真正控制行为的代码/配置              │
│       │                                                     │
│       ▼                                                     │
│  4. 最小修复        只改必要的部分                          │
│       │                                                     │
│       ▼                                                     │
│  5. 验证            测试所有场景                            │
│       │                                                     │
│       └──── 失败 ────▶ 回到步骤 1，不要继续打补丁           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: 观察现象

**必须使用 DevTools 或 Playwright**，而不是猜测。

### 检查清单

| 检查项 | 方法 |
|--------|------|
| 实际的 DOM 结构 | Elements 面板 |
| Computed styles | 查看 width/height/min-width/max-width 等 |
| 样式来源 | 看是哪个 CSS 规则在生效 |
| 是否有覆盖 | 查看被划掉的样式 |
| 布局模式 | table-layout / display / flex / grid |
| 事件是否触发 | Console 加 log 或 breakpoint |

### 使用 Playwright 检查

```javascript
// 获取元素的 computed style
const style = await page.$eval('selector', el => {
  const computed = window.getComputedStyle(el);
  return {
    width: computed.width,
    minWidth: computed.minWidth,
    maxWidth: computed.maxWidth,
    tableLayout: computed.tableLayout
  };
});
```

---

## Step 2: 理解机制

**在动手前，必须能回答以下问题：**

1. 这个组件/CSS 属性的工作原理是什么？
2. 哪些因素会影响它的行为？
3. 我要修改的代码，在整个流程中扮演什么角色？

### 常见机制陷阱

| 场景 | 陷阱 | 真相 |
|------|------|------|
| Ant Design Table 列宽 | 以为 `<th>` 的 width 控制列宽 | 实际由 `<colgroup>` + `scroll.x` 控制 |
| `scroll.x: 'max-content'` | 以为只是让表格可横向滚动 | 实际让浏览器忽略 width，根据内容计算 |
| Flexbox 子元素宽度 | 设置了 width 但不生效 | 需要同时设置 `flex-shrink: 0` |
| CSS `position: absolute` | 以为相对于父元素 | 实际相对于最近的 `position: relative` 祖先 |
| `transform` | 只是视觉变换 | 会影响 `position: fixed` 子元素的定位 |

### 如果不熟悉机制

1. 先查官方文档
2. 搜索 "X not working" / "X width ignored" 等关键词
3. 检查组件库源码
4. 创建最小复现 demo

---

## Step 3: 定位根因

**问自己：是我的代码问题，还是框架/机制问题？**

### 二分法排除

1. 移除可疑代码，看问题是否消失
2. 创建最小复现，逐步添加代码直到问题出现
3. 检查是否有其他 CSS/JS 在干扰

### 常见根因类型

| 类型 | 示例 | 修复方向 |
|------|------|----------|
| 配置问题 | `scroll.x: 'max-content'` 导致列宽失效 | 修改配置 |
| CSS 优先级 | 全局样式覆盖了组件样式 | 提高优先级或改选择器 |
| 组件 API 误用 | 用错了 prop 或 callback 签名 | 查文档，改用法 |
| 机制不匹配 | 想用 CSS 控制，但实际由 JS 控制 | 改用正确的控制方式 |
| 第三方库限制 | 库不支持这种用法 | 换方案或 fork |

---

## Step 4: 最小修复

**只改必要的部分，不引入新复杂度。**

### 原则

- 能用原生实现就不引入库
- 能改配置就不改代码
- 能改一处就不改多处
- 改完能解释清楚为什么这样改

### 反模式

| 反模式 | 问题 |
|--------|------|
| 引入新库解决小问题 | 增加依赖，可能带来新问题 |
| 到处加 `!important` | 掩盖问题，后续更难维护 |
| 在多个地方加补丁 | 说明没找到根因 |
| 改了生效但不知道为什么 | 下次还会踩坑 |

---

## Step 5: 验证

**测试所有场景，不只是出问题的那个。**

### 验证清单

- [ ] 原问题场景修复
- [ ] 相关场景没有回归
- [ ] 边界情况（空数据、超长内容、极小/极大值）
- [ ] 不同浏览器（如果需要）
- [ ] 响应式布局（如果需要）

### 失败后的处理

**如果验证失败，回到 Step 1 重新观察。**

禁止：
- 继续在当前方向打补丁
- 猜测 "可能是这个原因"
- 没观察就尝试下一个修复

---

## 案例：Ant Design Table 可拖拽列宽

### 错误路径（实际发生的）

```
问题：拖拽列宽时，某些列往左拖不动

尝试 1：用 react-resizable 库 → 失败
尝试 2：设置 minWidth/maxWidth → 失败  
尝试 3：改 CSS table-layout → 失败
尝试 4：改 transform → 失败
...（反复折腾 N 次）
最终：改 scroll.x → 成功
```

### 正确路径（应该这样做）

```
1. 观察：DevTools 检查 <th> 的 computed width
   → 发现 width 确实在变，但视觉没变

2. 理解：搜索 "ant design table column width not working"
   → 发现 scroll.x: 'max-content' 会让浏览器忽略 width

3. 定位：scroll.x 是根因

4. 修复：scroll.x 改成列宽总和

5. 验证：所有列都能正常拖拽

总耗时：10 分钟（而不是 N 小时）
```

---

## 触发条件

当遇到以下情况时，**必须**使用本方法论：

1. UI 行为不符合预期
2. CSS/样式不生效
3. 组件交互有问题（拖拽、点击、hover 等）
4. 布局错乱
5. 第一次尝试修复失败后

---

## 禁止事项

1. **禁止**不观察就动手改代码
2. **禁止**不理解机制就引入新库
3. **禁止**修复失败后继续猜测打补丁
4. **禁止**改了生效但说不清为什么

---

## 速查表

```
UI 问题 → DevTools 观察 → 理解机制 → 定位根因 → 最小修复 → 验证
              ↑                                        |
              └────────── 失败则回到这里 ──────────────┘
```
