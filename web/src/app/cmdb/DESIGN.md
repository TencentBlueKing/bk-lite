# 设计规范基线（DESIGN.md）

> 仅记录视觉、交互、文案与可访问性约定。不涉及模块结构、目录、技术选型。
> 作为新页面/新组件的视觉对齐基准。
> **适用范围**：本文档源于 CMDB 模块的设计审查，现已作为 web 端跨模块的设计基线使用，覆盖：**CMDB / 报警中心（alarm） / 运营分析（ops-analysis）**。后续模块加入时在 §15 增加分节即可。
> 本文档亦同步登记各模块已落地的修复与仍待修的平台级遗留问题。

---

## 1. 颜色

### 1.1 主题 token（必须优先使用）

| Token | 用途 |
|---|---|
| `var(--color-primary)` | 主操作、链接、focus ring |
| `var(--color-text-secondary)` | 次要文字 |
| `var(--color-text-3)` | 三级文字（副标题、辅助说明） |
| `var(--color-text-4)` | 四级文字（占位/弱化） |
| `var(--color-bg)` | 主容器背景 |
| `var(--color-bg-1)` | 次级容器/弱填充 |
| `var(--color-border)` / `var(--color-border-2)` | 边框（实线/虚线弱化） |
| `var(--color-modal-header-color)` | 弹窗头部底色 |
| `var(--color-fill-1)` | 拖拽侧栏/分组底色 |

### 1.2 场景语义色

承载业务语义的颜色（场景状态、变更类型）统一以"三元色（dot/bg/text）"成对出现，不要散落在行内 style：

| 语义 | 视觉示例 |
|---|---|
| 信息 / 普通变更 | 蓝（dot 强、bg 浅） |
| 失败 / 关系破坏 | 红（dot 强、bg 浅） |
| 成功 / 上线 | 绿 |
| 警告 / 提示 | 琥珀 |
| 配置 / 元数据 | 紫 |

**约定**：场景色集中维护为常量映射（如 `SCENARIO_COLORS`），暗色模式需独立给一套，不要"自动加滤镜"。

### 1.3 标签随机色

多标签场景（无业务语义的纯展示标签）走 hash 取色函数 `getTagColorByLabel(label)`，从一组预设里取，保证同 label 颜色稳定。**不要**为每个标签手挑颜色。

### 1.4 禁止

- 组件内直写 hex（`#155AEF` 之类）。必须迁到 token 或语义色映射。
- 用纯灰度表达成功/警告/错误，必须配语义色 + 图标/文字双通道。
- 通过亮度倒置实现暗色模式——必须独立配色。

---

## 2. 间距与尺寸

严格 4 / 8 倍数节奏。

| 用途 | 规范 |
|---|---|
| 卡片内边距 | `p-4`（16px） |
| 卡片圆角 | `rounded-xl`（12px）/ 内联块 `rounded-md`（6px） |
| 卡片阴影 | `shadow-md` |
| 区段纵向间距 | `mb-4`（16px）/ 大段落 `mb-5`（20px） |
| 元素间隙（按钮组/标签/字段） | **统一用父容器 `gap-2`**，不要在子按钮上挂 `mr-2`/`ml-[8px]`/`mr-[10px]` 散落间距 |
| 弹窗 footer 按钮组 | 父容器 `flex justify-end gap-2` |
| 输入控件最小高度 | 桌面 ≥ 40px / 移动 ≥ 44px（触摸目标） |
| 触摸目标 | ≥ 44×44px；不足时用 `hitSlop` 扩大热区 |

**禁止**：
- 任意像素值如 `mb-[13px]`。必须打破节奏时，**命名**到模块/全局常量。
- 高度低于触摸目标的可点击元素。

---

## 3. 字号与文字

### 3.1 尺度

| 类 | 场景 |
|---|---|
| `text-base`（16px） | 页面 H1 / 介绍标题 |
| `text-sm`（14px） | 正文 / 表格单元格 / 按钮 |
| `text-xs`（12px） | 辅助文字 / 时间戳 / 副标题 |

**禁止**：同元素同时声明 `text-xs text-sm`；正文低于 12px。

### 3.2 字重

| 类 | 场景 |
|---|---|
| `font-extrabold` | 强标题 |
| `font-semibold` | 卡片标题、表头 |
| `font-medium` | 标签、按钮 |
| `font-normal` | 正文 |

### 3.3 数字与对齐

- 数字列（年龄/价格/计数/时间戳）**必须**用 `font-variant-numeric: tabular-nums`，避免列内对齐抖动。
- 当前 `CustomTable` 全局未启用 tabular-nums，CMDB 内含数字的列需要**逐列**在 `render` 或 className 上加 `font-variant-numeric:tabular-nums` style；待平台级修复后可移除。

### 3.4 省略策略

| 场景 | 做法 |
|---|---|
| 单行省略 | `truncate` + `title={text}` 提供原文 |
| 多行省略 | `line-clamp-2` / `line-clamp-3` + hover 显示完整 |
| 表格单元格 | `ellipsis: { showTitle: false }` + `EllipsisWithTooltip` 组合 |

**禁止**：把 placeholder 当 label 用——必须有可见标签。

---

## 4. 按钮规范（CMDB 落地版）

> 已在本模块全量 sweep。新代码必须对齐下表 8 种形态，不要发明新组合。

### 4.1 8 种合法形态

| 类别 | type | size | danger | loading | icon | 文案 i18n key |
|---|---|---|---|---|---|---|
| 主 CTA / 创建 | `primary` | middle | – | 异步必 | 可选 `<PlusOutlined />` | `common.addNew` / `common.create` |
| 次要操作 | `default` | middle | – | – | 视情况 | — |
| 提交（弹窗主按钮） | `primary` | middle | – | **必须** | – | `common.confirm` |
| 取消（弹窗/抽屉） | `default` | middle | – | – | – | `common.cancel` |
| 破坏性 - 行内 | `link` | small / middle | **true** | 异步必 | – | `common.delete` |
| 破坏性 - 主按钮 | 留空（不写 type） | middle | **true** | 异步必 | – | `common.delete` / `common.batchDelete` |
| 行内文字操作（编辑/复制/查看） | `link` | small | – | – | – | `common.edit` / `common.copy` |
| 占位卡（仅 `assetManage/management/page.tsx:426`） | `dashed` | middle | – | – | `<PlusOutlined />` | `Model.addModel` |

### 4.2 破坏性操作三段式（已 sweep 落地）

```tsx
// 1) 行内删除按钮：type="link" + danger
<Button type="link" danger onClick={() => showDeleteConfirm(record)}>
  {t('common.delete')}
</Button>

// 2) 二次确认：okButtonProps 必带 danger
Modal.confirm({
  title: t('common.delConfirm'),
  content: t('common.delConfirmCxt'),
  okText: t('common.confirm'),
  cancelText: t('common.cancel'),
  okButtonProps: { danger: true },   // 必填
  centered: true,
  onOk: async () => { ... },
});

// 3) Popconfirm 内的删除按钮同样 danger
<Popconfirm title={...} onConfirm={...} okButtonProps={{ danger: true }}>
  <Button type="link" danger size="small">{t('common.delete')}</Button>
</Popconfirm>
```

### 4.3 异步按钮

- 所有触发 API 的按钮：`loading={state}` 防重复点击。
- 仅"打开 Modal"或"打开抽屉"的触发按钮**不**加 loading（异步在 Modal/抽屉内部已处理）。
- 弹窗主按钮必须配合一个布尔 state（如 `confirmLoading`/`saving`/`batchDeleting`）；不可裸异步。

### 4.4 间距统一

按钮组**不要**在子按钮上加 margin。统一用父容器：

```tsx
// ✅ 正确
<div className="flex justify-end gap-2">
  <Button>{t('common.cancel')}</Button>
  <Button type="primary">{t('common.confirm')}</Button>
</div>

// ❌ 禁止
<Button className="mr-[10px]">...</Button>
<Button className="ml-2">...</Button>
```

---

## 5. 表单

### 5.1 字段呈现

- 标签可见，与输入框上下对齐；不允许 placeholder 顶替 label。
- 必填字段标红色 `*`。
- 错误信息**紧邻字段**，不只在顶部汇总。
- 多错误时焦点自动回到第一个错误字段。

### 5.2 触发时机

- 校验时机：失焦（`onBlur`），不是每次按键。
- 异步提交按钮必须 `loading` + disabled，避免重复点击。

### 5.3 文本输入

| 字段类型 | 推荐控件 |
|---|---|
| 多行/长文本 | `<TextArea>` + `showCount` + `maxLength` |
| 邮箱/电话/数字 | 用 `type="email"` / `tel` / `number` 触发原生键盘 |
| 密码 | 自带 show/hide 切换 |

### 5.4 行内编辑（CMDB 落地版）

参考 `assetData/detail/baseInfo/list.tsx`：

```tsx
{item.isEdit ? (
  <>
    <Button type="link" size="small"
      aria-label={t('common.confirm')}
      icon={<CheckOutlined aria-hidden="true" />}
      onClick={() => confirmEdit(item.key)} />
    <Button type="link" size="small"
      aria-label={t('common.cancel')}
      icon={<CloseOutlined aria-hidden="true" />}
      onClick={() => cancelEdit(item.key)} />
  </>
) : (
  <>
    <PermissionWrapper requiredPermissions={['Edit']}>
      <Button type="link" size="small"
        aria-label={t('common.edit')}
        icon={<EditOutlined aria-hidden="true" />}
        onClick={() => enableEdit(item.key)} />
    </PermissionWrapper>
    <Button type="link" size="small"
      aria-label={t('common.copy')}
      icon={<CopyOutlined aria-hidden="true" />}
      onClick={() => onCopy(item, item.value)} />
  </>
)}
```

**约定**：图标按钮一律 **`aria-label` + 图标 `aria-hidden="true"`**。

---

## 6. 表格

### 6.1 必备

- 长文本单元格走省略 + tooltip，不要原生 `title` 属性。
- 操作列固定右侧（`fixed: 'right'`）。
- 数字列需逐列加 `font-variant-numeric:tabular-nums`（见 §3.3 平台级遗留）。
- 列头排序态用 `aria-sort` 朗读当前排序方向（待补）。

### 6.2 分页

- 默认页大小 20。
- 提供 `[10, 20, 50, 100]` 切换。
- 显示总数：「共 X 条」。

### 6.3 状态

| 状态 | 视觉 |
|---|---|
| 加载 | Skeleton 替代空白表头（不要"空表壳 + spinner"） |
| 空 | `Empty` + 简短文案 + 引导动作（"暂无数据，点此添加"） |
| 错误 | 红色提示 + retry 按钮 |
| 三态区分 | "未发起 / 无结果 / 失败" 文案不能复用同一句 |

### 6.4 大列表

超过 50 条**必须**虚拟化，不依赖浏览器原生滚动性能。

---

## 7. 弹窗与抽屉

### 7.1 标题区

- 主标题 + 可选副标题，视觉应有清晰层级（不同字号或不同颜色）。
- 副标题**应**作为独立 DOM 元素，便于屏幕阅读器分段朗读。
- 当前 `OperateModal` 实现把 title 与 subTitle 用字符串 `" - "` 拼接（见平台级遗留 §13），CMDB 业务页**不要**在 subTitle 内再用 `-` 加自定义后缀。

### 7.2 关闭与遮罩

- 右上角 ✕ 按钮：antd 已自带 `aria-label="Close"`，无需重复。
- Esc 必须可关闭；未保存变更需二次确认。
- 遮罩透明度 antd 默认 `rgba(0,0,0,0.45)`，在 40-60% 推荐区间，**不要**自定义降低。

### 7.3 选型

| 场景 | 选 |
|---|---|
| 创建/编辑一条记录 | `OperateModal`，宽度 600–800px |
| 详情侧栏 / 多视图切换 | `Drawer`，宽度 480–640px |
| 对比 / 差异两栏 | `Drawer`，宽度 ≥ 1200px |
| 列表 ⇄ 表单切换（订阅/规则） | `Drawer`，宽度 830px |
| 删除/破坏性确认 | `Modal.confirm`，centered，`okButtonProps:{ danger: true }` |

### 7.4 Footer

- 按钮组右对齐，主操作在最右。
- 仅一个 primary CTA；其余 default/text。
- 间距用父容器 `gap-2`（参见 §4.4）。
- 异步主按钮必须 `loading`。
- 危险操作主按钮 `danger`。

---

## 8. 标签 / 徽章

| 用途 | 做法 |
|---|---|
| 多标签紧凑展示 | `TagCapsuleGroup`，`maxVisible={2}` 溢出显示 `+N` + tooltip |
| 状态徽章 | 用语义色三元组（dot + bg + text），不只靠颜色——配 dot 圆点辅助识别 |
| 内建 vs 自定义 | 蓝 / 绿 区分（约定俗成） |

**禁止**：徽章里只放图标无文字（除非有 `aria-label`）。

---

## 9. 图标

### 9.1 来源

- **功能性图标**（编辑、删除、复制、搜索、上传、下载、关闭、展开、拖拽…）走 `@ant-design/icons`，不混用其他图形库或 emoji。
- **业务图标**（模型/资产类型自定义图形）走 iconfont，通过 `Icon` 组件渲染。

### 9.2 尺寸

| 场景 | 尺寸 |
|---|---|
| 行内表单按钮 | 14–16px |
| 卡片头部 | 24px |
| 模型/资产类型主图 | 36–40px |
| 状态点（dot） | 6–8px |

### 9.3 a11y（已落地）

| 模式 | 必须 |
|---|---|
| 图标按钮（无可见文字） | `<Button aria-label={t('...')} icon={<I aria-hidden="true" />} />` |
| 图标 + 文字按钮 | 图标 `aria-hidden="true"`，按钮文字承担可访问名 |
| 装饰性图标 | `aria-hidden="true"` |

**禁止**：emoji（🚀 ✅）作为功能图标。

---

## 10. 反馈与提示

### 10.1 Toast / Message

- 成功 `message.success` 3 秒自动消失。
- 错误 `message.error` 5 秒，必要时不自动消失，提供关闭。
- `aria-live="polite"`（不抢焦点）。

### 10.2 Loading

- 短任务（< 300ms）不显示 loading。
- 300ms–1s：按钮内 spinner（`loading` prop）。
- > 1s：Skeleton 替代具体 UI。
- 全页面 loading 仅用于首次进入；切换路由用骨架。

### 10.3 操作可撤销

- 删除/批量等破坏性操作，**优先**提供「撤销」toast（5 秒窗口），而非每次都拦截 Modal 确认。
- 不可撤销的操作（清空数据库类）才走 Modal.confirm + `danger`（参见 §4.2）。

### 10.4 进度

- 多步流程必须显示步骤指示器（Step）+ 当前步标号 + 允许后退。

---

## 11. 可访问性 / 键盘

| 模式 | 必须 |
|---|---|
| 可点击 `<div>` | 改用 `<button>`，或加 `role="button"` + `tabIndex={0}` + `onKeyDown`（Enter/Space） |
| 图标按钮 | `aria-label` 必填 |
| 焦点 | `:focus-visible` 必须有 2px 可见 ring（推荐 `outline: 2px solid var(--color-primary)` + `outline-offset: 2px`） |
| 颜色单一传达 | 加图标/文字辅助（成功 ✓ / 警告 ⚠ / 错误 ✗） |
| 表单错误 | 错误紧邻字段；首个错误自动获焦 |
| 模态弹层 | `role="dialog"` + `aria-modal="true"`（antd 默认）；Esc 可关；焦点 trap |
| 表格排序 | `aria-sort="ascending|descending|none"`（待补） |
| 标题层级 | 顺序 h1 → h6，不跳级 |

**对比度**（WCAG）：
- 正文 ≥ 4.5:1
- 大字号文字 ≥ 3:1
- UI 元素（边框、图标） ≥ 3:1

---

## 12. 动效 / 响应式 / 暗色

### 12.1 动效

| 场景 | 时长 | 缓动 |
|---|---|---|
| 微交互（按钮按下、hover） | 80–150ms | `ease-out` |
| 状态切换（展开/折叠） | 150–300ms | `ease-out` 进入 / `ease-in` 退出 |
| 弹窗进入 | 200ms | `ease-out` + scale 0.95 → 1 |
| 弹窗退出 | 150ms | 退出比进入快 ~70% |
| 复杂转场 | ≤ 400ms | spring 物理 |

**禁止**：动画作用于 `width/height/top/left`（改用 `transform`/`opacity`）；不可中断动画；无意义的长动画。
**必须**：尊重 `prefers-reduced-motion`，开启后动画降级。

### 12.2 响应式

- 移动优先：从最窄开始向大屏渐进增强。
- 工具栏/筛选条等横向控件组用 `flex flex-wrap gap-2`，窄屏自动换行。
- 不允许移动端横向滚动（除非显式的"轮播/数据卡片墙"）。
- 视口高度用 `min-h-dvh`（非 `100vh`）。

### 12.3 暗色模式

- 所有颜色必须走主题 token。
- 不依赖 `prefers-color-scheme`，由全局 `ThemeProvider` 驱动。
- 场景语义色需独立给一套暗色映射。

---

## 13. 文案

- 操作按钮：动词开头，简短。`保存` / `删除` / `导入资产` —— **不**用 `点击保存` / `操作`。
- 错误信息：**说明原因 + 给出修复路径**。`端口冲突，请关闭占用 8080 的服务` —— **不**用 `操作失败`。
- 空状态：解释为什么空 + 引导第一步。`暂无资产，点此 [创建模型]` —— **不**用 `无数据`。
- 占位符：示例值或格式提示，**不**重复 label。
- 时间：相对时间（`2 分钟前`）+ 鼠标悬浮显示绝对时间。
- 数字：千分位分隔，单位贴近数字（`1,234 台`）。

i18n key 沉淀：
- `common.delete` / `common.edit` / `common.copy` / `common.confirm` / `common.cancel` / `common.addNew` / `common.batchDelete`
- 删除二次确认：`common.delConfirm`（标题） + `common.delConfirmCxt`（正文）
- 新代码**禁止**重新发明同义 key（如 `common.del`、`common.remove`）。

---

## 14. 状态与零状态

每个数据视图必须明确处理四态，且**视觉与文案各异**：

| 态 | 视觉 | 文案示例 |
|---|---|---|
| 初始/未触发 | 引导式空态 + CTA | "选择一个模型开始查询" |
| 加载中 | Skeleton（结构提示） | — |
| 有数据 | 正常内容 | — |
| 数据为空 | Empty 插图 + 简短说明 + 创建入口 | "暂无数据，[添加第一条]" |
| 错误 | 红色提示 + retry | "加载失败，[重试]" |

**禁止**：四态合并到同一个空白 / 同一个 spinner / 同一句"无数据"。

---

## 15. 已落地修复登记（按模块）

> **改动性质共识**：所有登记项**仅追加 JSX prop**（`danger` / `aria-label` / `aria-hidden` / `okButtonProps` / `danger`/`role`/`tabIndex`/`onKeyDown`），**零业务逻辑变更**——onClick、状态、请求函数都没动过。

### 15.1 CMDB 模块（截至 2026-05-31）

| 类别 | 文件 | 改动 |
|---|---|---|
| **图标按钮 a11y** | `cmdb/(pages)/assetData/detail/baseInfo/list.tsx` | 行内编辑 4 个图标按钮（确认/取消/编辑/复制）加 `aria-label` + 图标 `aria-hidden="true"` |
| **图标装饰** | `cmdb/(pages)/assetData/page.tsx` | 顶部工具栏 4 个按钮内的 `UnorderedListOutlined`/`DownOutlined` 加 `aria-hidden="true"` |
| **删除按钮 danger** | `cmdb/(pages)/assetData/page.tsx` | 行内删除按钮加 `danger` |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/management/detail/uniqueRules/page.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/management/detail/associations/page.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/management/detail/autoAssociationRules/page.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/management/detail/attributes/page.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/soid/page.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx` | 同上 |
| **删除按钮 danger** | `cmdb/components/subscription/subscriptionRuleList.tsx` | Popconfirm 内删除按钮加 `danger` |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/page.tsx` | confirm 加 `okButtonProps:{danger:true}` |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/detail/layout.tsx` | 模型删除 confirm |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/detail/uniqueRules/page.tsx` | 同上 |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/detail/associations/page.tsx` | 单删 + 批量删 各一处 |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/detail/autoAssociationRules/page.tsx` | 同上 |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/detail/attributes/page.tsx` | 同上 |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/management/list/publicEnumLibraryModal.tsx` | 删除枚举库 Modal.confirm |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx` | 删除采集任务 Modal.confirm |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/soid/page.tsx` | 同上 |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetData/page.tsx` | `handleDeleteWithConfirm` |
| **删除 confirm okButtonProps** | `cmdb/(pages)/assetData/list/searchFilter.tsx` | 删除已保存筛选器 Modal.confirm |

### 15.2 报警中心（alarm）模块（截至 2026-06-01）

| 类别 | 文件 | 改动 |
|---|---|---|
| **图标按钮 a11y** | `alarm/components/k8sGuide/index.tsx` | 3 个复制按钮加 `aria-label={t('common.copy')}` + 图标 `aria-hidden="true"` |
| **图标按钮 a11y** | `alarm/components/zabbixGuide/index.tsx` | 3 个复制按钮同上 |
| **图标按钮 a11y** | `alarm/(pages)/incidents/components/collaboration/index.tsx` | "更多"图标按钮加 `aria-label={t('common.more')}` + `aria-hidden` |
| **删除按钮 danger** | `alarm/(pages)/settings/shieldStrategy/page.tsx` | 行删除按钮加 `danger` |
| **删除按钮 danger** | `alarm/(pages)/settings/alertAssign/page.tsx` | 同上 |
| **删除按钮 danger** | `alarm/(pages)/settings/correlationRules/page.tsx` | 同上 + Modal.confirm 加 `okButtonProps:{danger:true}` |
| **删除按钮 danger + 清色** | `alarm/(pages)/settings/globalConfig/components/levelManagementPanel.tsx` | 加 `danger`；顺手移除硬编码 `text-[#2F6BFF]` className（让 antd 走 token） |
| **删除 confirm okButtonProps** | `alarm/(pages)/settings/globalConfig/page.tsx` | 等级删除 Modal.confirm |
| **取消关联 confirm** | `alarm/(pages)/incidents/detail/page.tsx` | "取消关联告警" Modal.confirm 加 `okButtonProps:{danger:true}` |
| **通用删除 hook** | `alarm/hooks/useSettingsTable.ts` | 通用删除 Modal.confirm 加 `okButtonProps:{danger:true}` |
| **保守跳过** | `alarm/(pages)/alarms/components/alarmAction.tsx:103` | 动态 `type` 不明（可能是 resolve/close/delete 任意），未加 danger，等明确语义再处理 |
| **P1 语义色集中化（新增）** | `alarm/constants/colors.ts` | 新建集中常量文件：`BRAND` / `NEUTRAL` / `STATUS_TEXT` / `HEALTH_BG` / `SOURCE_LOGO` / `SOURCE_LOGO_FALLBACK` |
| **P1 替换 inline hex** | `alarm/(pages)/settings/alertAssign/page.tsx` | `'#00ba6c'` / `'#CE241B'` → `STATUS_TEXT.ACTIVE_GREEN` / `INACTIVE_RED` |
| **P1 替换 inline hex** | `alarm/(pages)/settings/shieldStrategy/page.tsx` | 同上 |
| **P1 替换 inline hex** | `alarm/(pages)/settings/globalConfig/page.tsx` | `'#F43B2C'` fallback → `BRAND.FAIL` |
| **P1 替换 inline hex** | `alarm/(pages)/settings/globalConfig/components/levelManagementPanel.tsx` | `'#FFAD42'` / `'#fff'` → `BRAND.LEVEL_FALLBACK_AMBER` / `NEUTRAL.ON_DARK_FG` |
| **P1 替换 inline hex** | `alarm/(pages)/settings/globalConfig/components/levelFormModal.tsx` | `'#fff'` → `NEUTRAL.ON_DARK_FG` |
| **P1 替换 inline hex** | `alarm/(pages)/integration/components/SummaryStats.tsx` | 6 处趋势色/SVG fill/iconBg → 对应常量引用 |
| **P1 重构** | `alarm/(pages)/integration/utils/health.ts` | 健康状态 6 元组 + LOGO_COLORS Map 改为引用集中常量 |
| **P1 替换 inline hex** | `alarm/constants/level.tsx` | `'#fff'` → `NEUTRAL.ON_DARK_FG` |

### 15.3 运营分析（ops-analysis）模块（截至 2026-06-01）

| 类别 | 文件 | 改动 |
|---|---|---|
| **图标按钮 a11y** | `ops-analysis/(pages)/view/dashBoard/index.tsx` | 裸 `<button>MoreOutlined`、`<Button>EditOutlined` 加 `aria-label`；`PlusOutlined` 图标加 `aria-hidden` |
| **图标按钮 a11y** | `ops-analysis/components/sidebar.tsx` | `MoreOutlined` 按钮加 `aria-label={t('common.more')}` + 图标 `aria-hidden` |
| **图标按钮 a11y** | `ops-analysis/(pages)/view/topology/components/toolbar.tsx` | `DeleteOutlined`/`SettingOutlined` 加 `aria-label` + 图标 `aria-hidden`（虽有 Tooltip 仍需 aria-label） |
| **删除按钮 danger** | `ops-analysis/(pages)/settings/dataSource/page.tsx` | 行删除按钮加 `danger` + Modal.confirm 加 `okButtonProps:{danger:true}` |
| **删除按钮 danger** | `ops-analysis/(pages)/settings/namespace/page.tsx` | 同上 |
| **删除 confirm okButtonProps** | `ops-analysis/components/sidebar.tsx` | 目录删除 Modal.confirm |
| **删除 confirm okButtonProps** | `ops-analysis/(pages)/view/dashBoard/index.tsx` | 移除 widget 的 Modal.confirm |
| **废弃 prop 迁移** | `ops-analysis/(pages)/view/page.tsx` | `okType:'danger'`（antd 已弃用）→ `okButtonProps:{danger:true}` |

### 15.4 P1 范围说明（语义色集中化）

- **alarm 模块已完成**（见 §15.2 末尾 9 行 P1 条目）：新建 `alarm/constants/colors.ts`，把所有 inline-style hex 替换为 import 引用，hex 值原样保留，视觉零变化。
- **ops-analysis 模块本批次不做**：该模块的语义色已分别落在 `topology/constants/nodeDefaults.ts`、`constants/common.ts`、`constants/threshold.ts` 三个常量文件，已天然集中，剩余散落主要是 Tailwind arbitrary class（`bg-[#1677ff15]` 等），不影响 import 集中化目标。改 Tailwind 需触配置或转 inline style，列入下一阶段。
- **共同未做**：所有 Tailwind arbitrary value 形式的 hex（`bg-[#xxx]`/`text-[#xxx]`/`border-[#xxx]`）。这部分需要 Tailwind config 引入 named colors 或大量 inline style 重写，风险与收益比不划算，登记在 §16 P3 项。

---

## 16. 平台级遗留（CMDB 无法独立解决，需推动共享组件层修复）

| Pri | 项 | 说明 |
|---|---|---|
| **P0** | `OperateModal` 标题副标题 DOM 分层 | 当前用 `" - "` 字符串拼接，屏幕阅读器把标题/副标题读成一句；CMDB 业务页只能在 subTitle 内规避使用 `-`，治本需改 `web/src/components/operate-modal/index.tsx` |
| **P0** | `CustomTable` 数字列 `tabular-nums` 全局化 | 当前要靠业务方逐列加 className；治本需改 `web/src/components/custom-table/index.module.scss` 加 `:global(.ant-table-cell){font-variant-numeric:tabular-nums}` |
| **P0** | `EntityList` 卡片键盘可达 + focus ring | 卡片是 `<div onClick>`，无 `role`/`tabIndex`/`:focus-visible`；治本需改 `web/src/components/entity-list/index.tsx` 加键盘交互与焦点环 |
| **P1** | `TimeSelector` 移动端水平溢出 | 容器缺 `flex-wrap`；治本需改 `web/src/components/time-selector/index.module.scss` |
| **P1** | Storybook 视觉伴随能力 | Storybook 启动链未就绪（依赖版本不兼容 + auth context mock 缺失）；CMDB 关键组件无法接入视觉回归 |
| **P1** | `compareDrawer.tsx` / `changeRecords/page.tsx` 硬编码 hex | 需先在主题层定义 design token，再批量替换 |
| **P2** | `assetSearch/page.tsx` 内联组件 `getInstDetial()` 拆分 | 影响性能 |
| **P2** | `assetManage/management/page.tsx` antd 桶式 import | 影响打包体积 |
| **P2** | "添加分组"按钮 type=default 应改 primary（B1） | 1 处特例需对齐 §4.1 主操作规范 |
| **P3** | 三态空状态文案统一 | 区分"未发起/无结果/失败" |
| **P3** | Drawer footer 抽 `<ModalFooter />` 组件 | 8+ 处复制粘贴 |

---

## 17. 提交新代码的自检清单

- [ ] 颜色全部走主题 token / 场景语义色映射，无散落 hex
- [ ] 间距严格 4/8 节奏；按钮组用父容器 `gap-2`，子按钮无 `mr-/ml-`
- [ ] 字号不同类同时声明（如 `text-xs text-sm`）
- [ ] 数字列加 `font-variant-numeric:tabular-nums`（直到平台级修复）
- [ ] 图标按钮有 `aria-label`，装饰图标有 `aria-hidden="true"`
- [ ] 可点击 `<div>` 已替换为 `<button>` 或补 `role/tabIndex/onKeyDown`
- [ ] `:focus-visible` ring 可见
- [ ] 异步按钮 `loading` 防重复
- [ ] **删除按钮 `danger`，删除确认 `okButtonProps:{danger:true}`**
- [ ] 按钮 8 种合法形态对照 §4.1，无新组合
- [ ] 列表四态文案区分（未触发 / 加载 / 空 / 错误）
- [ ] 文案：动词开头、错误带修复路径、空态带引导
- [ ] i18n key 复用 §13 沉淀，不发明同义 key
- [ ] 动效用 `transform`/`opacity`；尊重 `prefers-reduced-motion`
- [ ] 暗色模式独立校验对比度
- [ ] 移动端无横向滚动、控件 ≥ 44px 触摸目标

---

_文档反映 2026-05-31 时点的设计基线与本模块已落地修复。共享组件层遗留问题见 §16。新增模式或改约定时，请同步更新本文件。_
