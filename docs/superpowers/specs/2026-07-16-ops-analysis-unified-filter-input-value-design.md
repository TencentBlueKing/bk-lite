# 运营分析统一筛选器输入值修复设计

## 问题与根因

普通字符串筛选器由 `UnifiedFilterBar` 生成 Ant Design `Input` fallback。该输入框原本把 `ChangeEvent` 转换为 `event.target.value`，但 `ParamInputControl.renderFallback` 使用 `cloneElement` 再次覆盖 `onChange`，把其“直接值”回调传给了 Ant Design `Input`。因此用户输入“数据部”后，筛选本地状态第一次写入的是事件对象而非字符串；该对象序列化到请求中表现为 `{}`。

时间筛选器直接调用 `handleTimeRangeChange`，不经过 `ParamInputControl` fallback，所以 `billing_period` 正常。下拉与单选控件本身也已显式提取值。

## 修复设计

在 `ParamInputControl` 的 fallback 边界统一适配输入回调：如果回调参数具有 DOM 输入事件的 `target.value`，向上游传递 `target.value`；否则保留原来的直接值。这一修改作用于所有使用 input fallback 的普通筛选器，不依赖页面、筛选 ID 或参数名。

值为清空后的空字符串时必须原样传递，使搜索参数转换继续删除空筛选值；重置仍由 `UnifiedFilterBar` 按定义生成 `null` 或默认值，不改变现有逻辑。时间、select、radio、organization 分支不修改。

## 验证

增加一条聚焦回归测试，证明 DOM 输入事件被转换为“数据部”，直接字符串/数字/null 仍保持原值。随后运行该测试、现有运营分析参数控件测试及 TypeScript/ESLint 的相关文件检查。

## 范围

仅修改公共参数输入控件的 fallback 值适配及对应测试，不修改后端协议，不过滤请求中的空对象，不硬编码 `department`，不调整筛选绑定或时间筛选实现。
