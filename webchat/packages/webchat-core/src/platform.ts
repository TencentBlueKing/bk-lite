import type { ChatState, Message, PlatformContract, WebChatConfig } from './types';
import { assembleAguiHistoryParts, assembleAguiHistoryText } from './aguiHistoryText';

const TEMPLATE_TOKEN = /\{(\w+)\}/g;

export interface PlatformApplication {
  id: string;
  /** 列表展示名：渠道名；跨智能体重名时会带上智能体名 */
  name: string;
  /** SkillChannel binding id used by platform/web chat APIs. */
  channelId: string;
  skillId?: string;
  /** 所属智能体名称，用于跨智能体同名渠道消歧 */
  skillName?: string;
}

export interface PlatformSession {
  id: string;
  title: string;
  source?: string;
  updatedAt?: string;
}

export interface PlatformSelection {
  appId: string;
  sessionId: string;
}

export class PlatformAccessDeniedError extends Error {
  readonly status = 403;

  constructor(message = 'Platform chat applications are not accessible') {
    super(message);
    this.name = 'PlatformAccessDeniedError';
  }
}

export function isPlatformMode(
  config: Pick<WebChatConfig, 'platform' | 'sseUrl'> | null | undefined
): boolean {
  const platform = config?.platform;
  if (!platform) {
    return false;
  }
  return Boolean(
    platform.applicationsUrl &&
      platform.sessionsUrl &&
      platform.messagesUrl &&
      platform.chatUrlTemplate
  );
}

export function fillUrlTemplate(
  template: string,
  vars: Record<string, string | number | undefined | null>
): string {
  return template.replace(TEMPLATE_TOKEN, (_, key: string) => {
    const value = vars[key];
    return value === undefined || value === null ? '' : encodeURIComponent(String(value));
  });
}

export function unwrapPlatformPayload(body: unknown): unknown {
  if (body && typeof body === 'object' && 'result' in body && 'data' in body) {
    return (body as { data: unknown }).data;
  }
  return body;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function asRecordList(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) {
    return payload.filter(isRecord);
  }
  if (isRecord(payload)) {
    for (const key of ['results', 'items', 'data'] as const) {
      const nested = payload[key];
      if (Array.isArray(nested)) {
        return nested.filter(isRecord);
      }
    }
  }
  return [];
}

export function mapPlatformApplications(rows: Record<string, unknown>[]): PlatformApplication[] {
  const prepared = rows
    .map((item) => {
      const id = String(item.id ?? item.channel_id ?? '');
      const channelId = String(item.channel_id ?? item.id ?? '');
      const channelName =
        String(item.name ?? item.app_name ?? '').trim() ||
        String(item.skill_name ?? '').trim() ||
        (id ? `渠道 ${id}` : '');
      const skillName = String(item.skill_name ?? '').trim() || undefined;
      const skillId =
        item.skill_id === undefined || item.skill_id === null ? undefined : String(item.skill_id);
      return { id, channelName, channelId, skillId, skillName };
    })
    .filter((item) => item.id && item.channelId);

  const channelNameCounts = new Map<string, number>();
  for (const item of prepared) {
    channelNameCounts.set(item.channelName, (channelNameCounts.get(item.channelName) || 0) + 1);
  }

  const withDisplay = prepared.map((item) => {
    const collision = (channelNameCounts.get(item.channelName) || 0) > 1;
    // 渠道名与智能体名不同，或列表内渠道名撞车时，展示「渠道名（智能体名）」
    const name =
      item.skillName && (collision || item.skillName !== item.channelName)
        ? `${item.channelName}（${item.skillName}）`
        : item.channelName;
    return {
      id: item.id,
      name,
      channelId: item.channelId,
      skillId: item.skillId,
      skillName: item.skillName,
    };
  });

  const displayCounts = new Map<string, number>();
  for (const app of withDisplay) {
    displayCounts.set(app.name, (displayCounts.get(app.name) || 0) + 1);
  }

  // 智能体名也相同导致展示仍撞车时，追加 skillId
  return withDisplay.map((app) => {
    if ((displayCounts.get(app.name) || 0) <= 1 || !app.skillId) {
      return app;
    }
    return { ...app, name: `${app.name}#${app.skillId}` };
  });
}

function optionalTime(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim()) {
    return value;
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString();
  }
  return undefined;
}

export function mapPlatformSessions(rows: Record<string, unknown>[]): PlatformSession[] {
  return rows
    .map((item) => ({
      id: String(item.session_id ?? item.id ?? ''),
      title: String(item.title ?? '新会话'),
      source: typeof item.source === 'string' ? item.source : undefined,
      updatedAt: optionalTime(item.updated_at ?? item.created_at ?? item.first_time),
    }))
    .filter((item) => item.id);
}

export function formatSessionTime(value?: string, now = Date.now()): string | undefined {
  if (!value) {
    return undefined;
  }
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return undefined;
  }
  const delta = Math.max(0, now - timestamp);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < minute) return '刚刚';
  if (delta < hour) return `${Math.floor(delta / minute)} 分钟前`;
  if (delta < day) return `${Math.floor(delta / hour)} 小时前`;
  if (delta < 2 * day) return '昨天';
  if (delta < 30 * day) return `${Math.floor(delta / day)} 天前`;
  return `${Math.max(1, Math.floor(delta / (30 * day)))} 个月前`;
}

function extractMessageText(content: unknown): string {
  const assembled = assembleAguiHistoryText(content);
  if (assembled !== null) {
    return assembled;
  }
  if (typeof content === 'string') {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (isRecord(part) && typeof part.text === 'string') return part.text;
        if (isRecord(part) && typeof part.content === 'string') return part.content;
        if (isRecord(part) && typeof part.delta === 'string') return part.delta;
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  if (isRecord(content)) {
    if (typeof content.content === 'string') return content.content;
    if (typeof content.text === 'string') return content.text;
    if (typeof content.message === 'string') return content.message;
    if (typeof content.delta === 'string') return content.delta;
  }
  return content == null ? '' : String(content);
}

export function mapPlatformMessages(rows: Record<string, unknown>[]): Message[] {
  return rows
    .map((item, index) => {
      const role: Message['sender'] =
        item.conversation_role === 'user' || item.role === 'user' ? 'user' : 'bot';
      const timeValue = item.conversation_time ?? item.created_at ?? item.timestamp;
      const timestamp =
        typeof timeValue === 'number'
          ? timeValue
          : Date.parse(String(timeValue ?? '')) || Date.now() + index;
      const rawContent = item.conversation_content ?? item.content;
      const parts = assembleAguiHistoryParts(rawContent);
      const text = parts ? parts.text : extractMessageText(rawContent);
      const thinking = parts?.thinking?.trim() || '';
      return {
        id: String(item.id ?? `history_${index}`),
        type: 'text' as const,
        content: text,
        sender: role,
        timestamp,
        ...(thinking
          ? { metadata: { thinking, isThinking: false } }
          : {}),
      };
    })
    .filter((item) => String(item.content).trim() !== '' || Boolean(item.metadata?.thinking));
}

export function lastSessionStorageKey(prefix: string, userId: string, teamId: string): string {
  return `${prefix}:${userId}:${teamId}`;
}

export function dockCollapsedStorageKey(prefix: string, userId: string, teamId: string): string {
  return `${prefix}:collapsed:${userId}:${teamId}`;
}

/** Missing key or unreadable storage means collapsed (open when needed).
 * PlatformChat keeps dock chrome in memory; these helpers remain for hosts
 * that still want optional persistence. */
export function readDockCollapsed(
  storage: Pick<Storage, 'getItem'> | null | undefined,
  key: string
): boolean {
  if (!storage) {
    return true;
  }
  try {
    return storage.getItem(key) !== '0';
  } catch {
    return true;
  }
}

export function writeDockCollapsed(
  storage: Pick<Storage, 'setItem'> | null | undefined,
  key: string,
  collapsed: boolean
): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, collapsed ? '1' : '0');
  } catch {
    // Ignore quota / private-mode failures.
  }
}

export function readLastSelection(
  storage: Pick<Storage, 'getItem'> | null | undefined,
  key: string
): PlatformSelection | null {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PlatformSelection;
    if (!parsed?.appId || !parsed?.sessionId) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeLastSelection(
  storage: Pick<Storage, 'setItem'> | null | undefined,
  key: string,
  selection: PlatformSelection
): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(key, JSON.stringify(selection));
  } catch {
    // Ignore quota / private-mode failures; chat still works without restore.
  }
}

export function resolvePlatformSelection(
  apps: PlatformApplication[],
  sessions: PlatformSession[],
  stored: PlatformSelection | null
): { app: PlatformApplication | null; sessionId: string | null } {
  if (apps.length === 0) {
    return { app: null, sessionId: null };
  }
  const app = apps.find((item) => item.id === stored?.appId) ?? apps[0];
  const restoreStoredSession =
    stored?.appId === app.id && sessions.some((item) => item.id === stored.sessionId);
  const sessionId = restoreStoredSession ? stored!.sessionId : sessions[0]?.id ?? null;
  return { app, sessionId };
}

export function createPlatformSessionId(): string {
  return `session_${Date.now()}`;
}

export function isPlatformDraftSession(
  sessionId: string | null | undefined,
  sessions: Array<{ id: string }>
): boolean {
  return Boolean(
    sessionId?.startsWith('session_') && !sessions.some((item) => item.id === sessionId)
  );
}

export function shouldFetchPlatformMessages(input: {
  sessionId: string | null;
  loadedSessionId: string | null;
  sessions: Array<{ id: string }>;
}): boolean {
  if (!input.sessionId) {
    return false;
  }
  if (isPlatformDraftSession(input.sessionId, input.sessions)) {
    return false;
  }
  return input.loadedSessionId !== input.sessionId;
}

export function isPersistedPlatformSession(
  sessionId: string | null | undefined,
  sessions: PlatformSession[]
): boolean {
  return Boolean(sessionId && sessions.some((item) => item.id === sessionId));
}

export function sessionTitleFromUserContent(content: Message['content'], max = 50): string {
  let text = '';
  if (typeof content === 'string') {
    text = content;
  } else if (Array.isArray(content)) {
    text = content
      .map((part) => (typeof part.message === 'string' ? part.message : part.text) || '')
      .join('');
  }
  text = text.trim().replace(/\s+/g, ' ');
  if (!text) return '新会话';
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

/** 发完一轮后才拉历史：握手阶段的 connected 不刷新，避免会话还没落库。 */
export function shouldRefreshPlatformSessions(from: ChatState, to: ChatState): boolean {
  return to === 'idle' || (from === 'chatting' && to === 'connected');
}

/** Drop a session from the list. If it was current, `currentId` becomes null. */
export function removePlatformSession(
  sessions: PlatformSession[],
  deletedId: string,
  currentId: string | null
): { sessions: PlatformSession[]; currentId: string | null } {
  return {
    sessions: sessions.filter((item) => item.id !== deletedId),
    currentId: currentId === deletedId ? null : currentId,
  };
}

export function isRequiredPlatformContract(
  platform: PlatformContract | undefined
): platform is PlatformContract {
  return isPlatformMode({ platform });
}

/** Host shell reads this to inset page content while the dock is open. */
export const WEBCHAT_DOCK_INSET_VAR = '--bk-webchat-dock-width';
export const PLATFORM_DOCK_CHAT_WIDTH = 380;
export const PLATFORM_HISTORY_RAIL_DOCK = 176;

/**
 * Empty published-app list: hide the launcher unless the host says this user
 * can publish/enable agents (`canManageAgents: true`). `undefined` keeps the
 * legacy empty-state launcher for embeds that do not pass the flag.
 */
export function shouldShowPlatformLauncher(input: {
  appCount: number;
  canManageAgents?: boolean;
}): boolean {
  return input.appCount > 0 || input.canManageAgents !== false;
}

/** Width the host should reserve. Fullscreen covers the page, so inset is 0. */
export function platformDockInsetWidth(input: {
  visible: boolean;
  fullscreen?: boolean;
  historyOpen?: boolean;
}): number {
  if (!input.visible || input.fullscreen) {
    return 0;
  }
  return input.historyOpen
    ? PLATFORM_DOCK_CHAT_WIDTH + PLATFORM_HISTORY_RAIL_DOCK
    : PLATFORM_DOCK_CHAT_WIDTH;
}
