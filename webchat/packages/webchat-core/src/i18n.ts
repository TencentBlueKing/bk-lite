/**
 * WebChat 语言层
 *
 * webchat 是独立打包的通用包（不依赖 web 主应用的 React Context），因此自带一份
 * 零依赖的 zh/en 词条与翻译函数。宿主（如 BK-Lite web）通过 `locale` 配置传入
 * 当前语言；未传时默认中文，保持既有行为不变。
 *
 * 词条缺 key 时回退到调用方给的 fallback，再回退到 key 本身，
 * 语义与 web 侧 `web/src/utils/i18n.ts` 的 `t(id, defaultMessage?, values?)` 一致。
 */

export type Locale = 'zh' | 'en';

export const DEFAULT_LOCALE: Locale = 'zh';

export type TranslateValues = Record<string, string | number>;

export type Translate = (key: string, fallback?: string, values?: TranslateValues) => string;

/** `{name}` 占位替换，避免为 webchat 引入完整 ICU 依赖。 */
const interpolate = (template: string, values?: TranslateValues): string => {
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = values[key];
    if (value == null) {
      return match;
    }
    return String(value);
  });
};

const zh: Record<string, string> = {
  // ── 会话 ────────────────────────────────────────────────────────────────
  'session.new': '新会话',
  'session.channelFallback': '渠道 {id}',
  'session.justNow': '刚刚',
  'session.minutesAgo': '{count} 分钟前',
  'session.hoursAgo': '{count} 小时前',
  'session.yesterday': '昨天',
  'session.daysAgo': '{count} 天前',
  'session.monthsAgo': '{count} 个月前',

  // ── 输入 ────────────────────────────────────────────────────────────────
  'chat.inputPlaceholder': '请输入消息...',
  'chat.send': '发送',
  'chat.stop': '停止',

  // ── 面板标题与操作 ──────────────────────────────────────────────────────
  'chat.fullscreen': '全屏',
  'chat.exitFullscreen': '退出全屏',
  'chat.close': '关闭',
  'chat.closeConversation': '关闭对话',
  'chat.clearConversation': '清除对话',
  'chat.openConversation': '打开对话',
  'chat.switchAgent': '切换智能体',
  'chat.newConversation': '新对话',
  'chat.historySessions': '历史会话',
  'chat.collapseHistory': '收起历史',
  'chat.headerTitle': '会话',
  'chat.defaultAssistantName': '平台助手',
  'chat.floatingSubtitle': '随时为你提供帮助',
  'chat.floatingDragHint': '打开对话，按住可拖动',
  'chat.floatingNewChat': '新对话',
  'chat.floatingClose': '关闭',

  // ── 消息状态 ────────────────────────────────────────────────────────────
  'chat.thinking': '思考中',
  'chat.replying': '正在回复',
  'chat.organizing': '正在整理思路',
  'chat.analyzingToolResult': '正在分析工具结果',
  'chat.thoughtFor': '思考了 {count} 秒',
  'chat.thinkingDone': '已完成思考',
  'chat.emptyStart': '发一条消息开始对话',
  'chat.defaultError': '未知错误',
  'chat.errorTitle': '错误',

  // ── 图片 ────────────────────────────────────────────────────────────────
  'image.limitPerMessage': '每条消息最多选择 {count} 张图片，本批次未添加。',
  'image.totalSizeLimit': '每条消息的图片总大小不能超过 {count}MB，本批次未添加。',
  'image.pixelsLimit': '{scope}不能超过 {count} 百万像素，本批次未添加。',
  'image.pixelsScopeSingle': '单张图片',
  'image.pixelsScopeTotal': '每条消息的图片总计',
  'image.fileTooLarge': '图片"{name}"超过 {count}MB 大小限制，已跳过。',
  'image.pastedTooLarge': '粘贴的图片超过 {count}MB 大小限制，已跳过。',
  'image.addedPlaceholder': '{name} 已添加（安全占位，不在浏览器预览）',
  'image.sentNotPreviewable': '图片已发送（格式未在浏览器解码预览）',
  'image.readAborted': '图片尺寸读取已取消。',
  'image.readFileAborted': '图片读取已取消。',
  'image.readFailed': '读取图片“{name}”失败。',
  'image.readCancelled': '读取图片“{name}”已取消。',

  // ── 消息操作 ────────────────────────────────────────────────────────────
  'message.copy': '复制',
  'message.copied': '已复制到剪贴板',
  'message.regenerate': '重新生成',
  'message.delete': '删除',
  'message.deleteConfirmTitle': '是否删除该条消息？',
  'message.deleteConfirmBody': '删除后，聊天记录不可恢复，对话内的文件也将被彻底删除。',

  // ── 会话面板 ────────────────────────────────────────────────────────────
  'sessions.title': '历史对话',
  'sessions.loading': '加载中…',
  'sessions.empty': '暂无会话',
  'sessions.deleting': '删除中',
  'sessions.delete': '删除',
  'sessions.deleteConfirmTitle': '删除会话',
  'sessions.deleteConfirmBody': '确定要删除这个会话吗？删除后无法恢复。',
  'sessions.clearConfirmTitle': '你即将清除当前对话，清除后将无法恢复，是否继续清除?',
  'sessions.clearConfirmBody': '删除后，聊天记录不可恢复，对话内的文件也将被彻底删除。',
  'sessions.clearConfirmAction': '清除对话',
  'sessions.accessibleName': '历史会话',

  // ── 智能体空态 ──────────────────────────────────────────────────────────
  'agents.emptyTitle': '还没有可对话的智能体',
  'agents.emptyHint': '请先发布智能体，并在详情中开通「平台」渠道。开通后即可在这里对话。',
  'agents.manageCta': '前往智能体列表',

  // ── 通用操作 ────────────────────────────────────────────────────────────
  'common.confirm': '确定',
  'common.cancel': '取消',
  'common.loading': '加载中…',

  // ── 人工审批 ────────────────────────────────────────────────────────────
  'hitl.title': '需要审批',
  'hitl.approve': '通过',
  'hitl.reject': '拒绝',
  'hitl.pleaseSelect': '请选择',
  'hitl.submitFailed': '提交失败，请重试',

  // ── 工具调用 ────────────────────────────────────────────────────────────
  'tool.running': '正在使用',
  'tool.used': '已使用',
  'tool.params': '参数',
  'tool.result': '结果',

  // ── 上下文用量 ──────────────────────────────────────────────────────────
  'context.title': '上下文用量',
  'context.segment.system': '系统提示',
  'context.segment.tools': '工具定义',
  'context.segment.skills': '技能包',
  'context.segment.wiki': 'Wiki 注入',
  'context.segment.summary': '已压缩摘要',
  'context.segment.conversation': '对话',
  'context.nextPacket': '下一次发给模型的包',
  'context.percentUsed': '{percent}% 已用',
  'context.packetOverBudget': '约 {packet} / {budget}',
  'context.emptyHint': '发一条消息后，这里会显示下一次发给模型的包占了多少输入工作预算。',
  'context.budgetExplainer':
    '分母是输入工作预算（模型窗口 {window}）。压缩线约 {compact}。',
  'context.summaryExplainer': '界面上的历史还在；发给模型的包里，更早的轮次已收成摘要。',
  'context.nearBudgetExplainer':
    '接近输入工作预算。再变长会继续压缩；系统提示和本轮问题放不下时才会失败。',
};

const en: Record<string, string> = {
  // ── Sessions ────────────────────────────────────────────────────────────
  'session.new': 'New conversation',
  'session.channelFallback': 'Channel {id}',
  'session.justNow': 'just now',
  'session.minutesAgo': '{count} min ago',
  'session.hoursAgo': '{count} h ago',
  'session.yesterday': 'yesterday',
  'session.daysAgo': '{count} d ago',
  'session.monthsAgo': '{count} mo ago',

  // ── Input ───────────────────────────────────────────────────────────────
  'chat.inputPlaceholder': 'Type a message...',
  'chat.send': 'Send',
  'chat.stop': 'Stop',

  // ── Panel titles and actions ─────────────────────────────────────────────
  'chat.fullscreen': 'Full screen',
  'chat.exitFullscreen': 'Exit full screen',
  'chat.close': 'Close',
  'chat.closeConversation': 'Close chat',
  'chat.clearConversation': 'Clear conversation',
  'chat.openConversation': 'Open chat',
  'chat.switchAgent': 'Switch agent',
  'chat.newConversation': 'New chat',
  'chat.historySessions': 'Chat history',
  'chat.collapseHistory': 'Collapse history',
  'chat.headerTitle': 'Conversations',
  'chat.defaultAssistantName': 'Platform assistant',
  'chat.floatingSubtitle': 'Always here to help',
  'chat.floatingDragHint': 'Open chat, hold to drag',
  'chat.floatingNewChat': 'New chat',
  'chat.floatingClose': 'Close',

  // ── Message status ──────────────────────────────────────────────────────
  'chat.thinking': 'Thinking',
  'chat.replying': 'Replying',
  'chat.organizing': 'Putting thoughts together',
  'chat.analyzingToolResult': 'Analyzing tool results',
  'chat.thoughtFor': 'Thought for {count}s',
  'chat.thinkingDone': 'Finished thinking',
  'chat.emptyStart': 'Send a message to start',
  'chat.defaultError': 'Unknown error',
  'chat.errorTitle': 'Error',

  // ── Images ──────────────────────────────────────────────────────────────
  'image.limitPerMessage': 'At most {count} images per message; this batch was skipped.',
  'image.totalSizeLimit': 'Total image size per message cannot exceed {count}MB; this batch was skipped.',
  'image.pixelsLimit': '{scope} cannot exceed {count} megapixels; this batch was skipped.',
  'image.pixelsScopeSingle': 'A single image',
  'image.pixelsScopeTotal': 'All images in a message',
  'image.fileTooLarge': 'Image "{name}" exceeds {count}MB and was skipped.',
  'image.pastedTooLarge': 'Pasted image exceeds {count}MB and was skipped.',
  'image.addedPlaceholder': '{name} added (safe placeholder, not previewed)',
  'image.sentNotPreviewable': 'Image sent (format not previewed in browser)',
  'image.readAborted': 'Image size read was cancelled.',
  'image.readFileAborted': 'Image read was cancelled.',
  'image.readFailed': 'Failed to read image "{name}".',
  'image.readCancelled': 'Reading image "{name}" was cancelled.',

  // ── Message actions ─────────────────────────────────────────────────────
  'message.copy': 'Copy',
  'message.copied': 'Copied to clipboard',
  'message.regenerate': 'Regenerate',
  'message.delete': 'Delete',
  'message.deleteConfirmTitle': 'Delete this message?',
  'message.deleteConfirmBody': 'Deleting removes the chat history and any files in it for good.',

  // ── Session panel ───────────────────────────────────────────────────────
  'sessions.title': 'Chat history',
  'sessions.loading': 'Loading…',
  'sessions.empty': 'No conversations',
  'sessions.deleting': 'Deleting',
  'sessions.delete': 'Delete',
  'sessions.deleteConfirmTitle': 'Delete conversation',
  'sessions.deleteConfirmBody': 'Delete this conversation? This cannot be undone.',
  'sessions.clearConfirmTitle': 'You are about to clear this conversation. This cannot be undone. Continue?',
  'sessions.clearConfirmBody': 'Deleting removes the chat history and any files in it for good.',
  'sessions.clearConfirmAction': 'Clear conversation',
  'sessions.accessibleName': 'Chat history',

  // ── Agent empty state ───────────────────────────────────────────────────
  'agents.emptyTitle': 'No agent to chat with yet',
  'agents.emptyHint': 'Publish an agent first and enable its Platform channel in the details page.',
  'agents.manageCta': 'Go to agent list',

  // ── Common actions ──────────────────────────────────────────────────────
  'common.confirm': 'OK',
  'common.cancel': 'Cancel',
  'common.loading': 'Loading…',

  // ── Human-in-the-loop approval ──────────────────────────────────────────
  'hitl.title': 'Approval required',
  'hitl.approve': 'Approve',
  'hitl.reject': 'Reject',
  'hitl.pleaseSelect': 'Please select',
  'hitl.submitFailed': 'Submit failed, please retry',

  // ── Tool calls ──────────────────────────────────────────────────────────
  'tool.running': 'Using',
  'tool.used': 'Used',
  'tool.params': 'Parameters',
  'tool.result': 'Result',

  // ── Context usage ───────────────────────────────────────────────────────
  'context.title': 'Context usage',
  'context.segment.system': 'System prompt',
  'context.segment.tools': 'Tool definitions',
  'context.segment.skills': 'Skill packages',
  'context.segment.wiki': 'Wiki injection',
  'context.segment.summary': 'Compressed summary',
  'context.segment.conversation': 'Conversation',
  'context.nextPacket': 'Next packet to the model',
  'context.percentUsed': '{percent}% used',
  'context.packetOverBudget': 'about {packet} / {budget}',
  'context.emptyHint': 'After you send a message, this shows how much of the input budget the next model packet uses.',
  'context.budgetExplainer': 'The denominator is the input working budget (model window {window}). Compaction starts around {compact}.',
  'context.summaryExplainer': 'History is still on screen; earlier turns are summarized in what we send to the model.',
  'context.nearBudgetExplainer': 'Close to the input working budget. Longer content gets compacted further; it only fails when the system prompt and the current question no longer fit.',
};

const catalogs: Record<Locale, Record<string, string>> = { zh, en };

/** 供测试与宿主校验「两侧 key 集合一致」；运行时无需使用。 */
export const webChatCatalogs = catalogs;

export const normalizeLocale = (locale?: string | null): Locale =>
  locale === 'en' || locale?.toLowerCase().startsWith('en') ? 'en' : DEFAULT_LOCALE;

let currentLocale: Locale = DEFAULT_LOCALE;

/** 供 React 树外的模块级代码（imageBudget 等）取当前语言。 */
export const setWebChatLocale = (locale?: string | null): Locale => {
  currentLocale = normalizeLocale(locale);
  return currentLocale;
};

export const getWebChatLocale = (): Locale => currentLocale;

/**
 * 创建翻译函数。缺 key 时依次回退到 `fallback`、key 本身。
 * `override` 用于宿主注入自定义词条（优先于内置词条）。
 */
export const createTranslator = (
  locale?: string | null,
  override?: Partial<Record<Locale, Record<string, string>>>,
): Translate => {
  const resolved = normalizeLocale(locale);
  const custom = override?.[resolved];
  const base = catalogs[resolved];
  return (key, fallback, values) => {
    const message = custom?.[key] ?? base[key] ?? fallback ?? key;
    return interpolate(message, values);
  };
};

/** 使用当前全局 locale 的翻译函数。 */
export const translate: Translate = (key, fallback, values) =>
  createTranslator(currentLocale)(key, fallback, values);

export type WebChatCatalog = Record<string, string>;
