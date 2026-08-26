# 页面内容对话对接规范

其它 app（告警、CMDB、日志、作业、运营分析等）要把「当前页面」接到右下角悬浮机器人，按本文做。产品与架构见同目录 [`spec.md`](./spec.md)（含修订 v2 / v3）；监控参考实现见 `web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`。

对接完成后：用户在本页打开机器人提问时，模型能看到**当轮**页面快照。未登记的页面保持普通对话，不携带当前页快照。

---

## 1. 你不用改什么

| 层 | 已有能力 |
|---|---|
| 对话框 | **每轮发送默认采集**页面上下文（已去掉「已附加当前页面」chip）；registry 无匹配 pilot 时不携带快照 |
| `GlobalWebchat` | 发送前 `collectContext`，快照进 POST `page_context` |
| 后端 `skill_channel` | 快照只注入当前轮、**不落会话历史**；按问题聚焦图表；**本轮点名图表时丢掉对话历史**（防旧时间窗结论）；非多模态模型自动去图留 caption；单轮/会话超限错误流 |

嵌入式渠道、IM 不在本能力范围。

**业务页面代码默认零改动**：筛选、切视图、数据刷新等内存态，优先在 `*.pilot.ts` 里用 URL / DOM / echarts `getOption()` 嗅探；不要为了对接去改业务组件。

---

## 2. 硬约束

1. **惰性**：未打开机器人、未发送时不得采集；发送时才 `collect`。
2. **零展示侵入**：只读 DOM / URL / echarts 实例；**不改业务组件与图表 option**。
3. **图表走截图**：用公共模块 `@/components/chart-snapshot`（约 600px JPEG，最多 6 张 + caption），不喂原始时序。
4. **失败不挡发送**：pilot 超时/失败 `console.debug` 后跳过。
5. **敏感信息**：禁止凭据、token、密钥。
6. **运行时解耦**：app 可 import `chart-snapshot` 与 `import type` 契约类型；**不要** import opspilot 业务模块。opspilot 未加载时其它页面不得异常。

---

## 3. 接入步骤（Pilot）

1. 与页面同目录新建 `*.pilot.ts`（Next 不会当成路由）。
2. 导出两个函数：

```ts
import type {
  AiPageContext,
  PageContextCollectHint,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';

export function getMessage(): PageContextMessage {
  // title 由接入方定义（可写死或拼 ID）；用作缓存 key，重名自负。
  // currentTime 须在「筛选 / 切视图 / 数据刷新」后变化；省略则每轮重采。
  return { title: `alarm-list:${status}`, currentTime: lastRefreshAt };
}

export async function getContext(
  toolkit: PageContextToolkit,
  _hint?: PageContextCollectHint,
): Promise<Partial<AiPageContext>> {
  // 全量采集；前端不再按用户问题筛图。
  const images = await toolkit.captureEchartsFromDoms(chartDoms, 6);
  return {
    app: 'alarm',
    title: document.title,
    sections: [/* identity + 时间筛选（如有）+ visible-charts */],
    images,
  };
}
```

3. 保存后重启 / 跑一次 `pnpm prepare-enterprise`：codegen 扫描 `src/app/**/*.pilot.ts` 生成 `pilots.generated.ts`（提交进 git）。**不必**再手改 `pilots.ts`。

路由由文件位置推导（去掉 `(group)`，目录做 pathname 前缀）。pilot 必须与所服务页面同目录。

Hook `useAiPageContext` 仍可用，适合仅存于 React state、DOM 读不到的选中项；与 pilot 可并存。只有在 DOM/URL 实在读不到、又必须稳定指纹时，才考虑改业务页暴露信号——**默认不要改**。

---

## 4. 筛选变更与 `currentTime`（不改原页面）

时间筛选、Tab、组织等往往只在 React state 里，**不一定进 URL**。对接约定：

| 做法 | 说明 |
|---|---|
| **推荐** | 在 `getMessage` 里拼 `currentTime`：可读的筛选文案 + 页面上可见的数据指纹（KPI 文案、状态标签等） |
| **读 DOM** | 从工具栏 / 卡片 class 取文本（监控示例：`toolbarTimeSelector`、`statValue`、`uptimeStatusMain`） |
| **读图表** | `captionFromOption` / 截图已反映当前渲染窗口；unix 秒序列会自动带 `横轴: HH:mm~HH:mm` |
| **不推荐** | 仅为对接去改业务页把筛选写入 URL 或抛全局事件 |

### 监控仪表盘参考（`dashboard.pilot.ts`）

- `currentTime` ≈ `时间筛选文案 :: KPI 瞬时值指纹 :: 采集状态 :: 运行状态`
- sections 写明「当前筛选」「KPI 快照」；图表 caption 可含 `横轴: …`
- 发送采集时 Console：`[ai-page-context] page data updated at …`（含 `timeRange` / `charts`），便于核对是否重采

### 关于 KPI 数字

健康概览 KPI 取的是时间窗**末端瞬时值**，不是窗口平均。切「最近15分钟」与「最近6小时」时，headline 百分比可能相同；真正变化的是趋势图形态、采集时间线、运行状态（如「期间有重启」）以及 caption 里的横轴。`currentTime` 应把**筛选文案**算进去，不能只靠 KPI 数字。

发消息前请等筛选对应的图表加载完成，再提问。

---

## 5. 快照契约

```ts
{
  url?: string;
  app?: string;
  title?: string;
  sections?: { id: string; label: string; content: string; priority?: number }[];
  images?: { caption?: string; dataUrl: string }[];
}
```

- 文本合计约 8K；截图最多 6 张。
- caption 第一段（`；` 前）必须是稳定图名，服务端靠它聚焦。推荐格式：
  - `CPU 时间分布；序列: …`
  - 趋势图：`系统负载趋势；序列: …；横轴: 08:25~14:14；最新值: …`
- 页面上下文**只注入当轮**用户消息（`<current_page>` + 可选 `image_url`），**不写入会话历史**；下一轮会再采一份最新快照。
- 所有提问统一按页面问答处理；未登记路由则无快照（裸聊）。

---

## 6. 缓存（前端 registry）

opspilot registry 内存 Map：`title → { currentTime, content }`。

- `getMessage` 每轮必调。
- `title` + `currentTime` 未变 → 复用上次 `getContext` 结果。
- `currentTime` 缺失或变化 → 重新 `getContext`（筛选变更必须让 `currentTime` 变）。

---

## 7. 服务端：聚焦、丢历史、超限、多模态

| 行为 | 规则 |
|---|---|
| 聚焦 | 问题点名图表时，只保留匹配截图与对应 caption 列表 |
| **丢历史** | 本轮已点名任一图表 → **整段 `chat_history` 清空**再调模型（避免同一张图换时间筛选后仍复述上一问的旧时间窗）。未点名图表的追问仍保留历史 |
| 引导语 | 时间范围 / 横轴 / KPI **一律以本轮 `<current_page>` 为准**，禁止沿用历史里过期的时间窗描述 |
| 单轮过大 | 「当前页面内容过多，无法进行问答」 |
| 会话累计过大 | 「上下文过长，请新开会话」 |
| 非多模态 | `LLMModel.is_multimodal=false` 时丢掉全部图片，保留文本与 caption |

---

## 8. 验收

1. 已登记页：发送请求带 `page_context`；未登记页：无 `page_context`（裸聊）。
2. 总览提问能用到本页对象/图。
3. 点名单图：服务端只留匹配图；`history_messages=0`（看 `opspilot.log` 的 `page_context ingest`）。
4. **切换时间筛选后**：Console 指纹中 `timeRange` / `横轴` 变化；新会话提问应对齐新窗口（勿沿用旧会话里旧时间窗的回答）。
5. 页面展示与接入前一致；业务页无仅为对接的展示改动。

---

## 9. 禁止事项

- 改业务页组件仅为对接（默认只动 `*.pilot.ts`）。
- 页面加载时预截图。
- dump 全表 / 原始时序进 sections。
- 改 webchat / GlobalWebchat / skill_channel 注入（扩框架另评）。
- 把「只有本 app 用」的采集塞进 `src/components`（共享须 ≥2 app；截图已是公共 `chart-snapshot`）。
- 指望 KPI headline 随时间窗「明显变数」——瞬时值可能相同，应用筛选文案 + 横轴 + 状态文案做指纹。

## 10. 提交清单

- [ ] 新增 `*.pilot.ts`（`getMessage` + `getContext`）
- [ ] `currentTime` 覆盖筛选 / 刷新（可读 DOM 或业务已有时间戳）
- [ ] 跑过 prepare-enterprise / 提交更新后的 `pilots.generated.ts`（若有 diff）
- [ ] caption 图名稳定；有趋势则尽量含 `横轴`；有图则有 `visible-charts`
- [ ] 无凭据、无全表 dump
- [ ] 未改业务页展示
- [ ] 按第 8 节手测（含筛选变更）
