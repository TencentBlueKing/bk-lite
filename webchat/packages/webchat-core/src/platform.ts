import type { Message, PlatformContract, WebChatConfig } from './types';
import { assembleAguiHistoryText } from './aguiHistoryText';

const TEMPLATE_TOKEN = /\{(\w+)\}/g;

export interface PlatformApplication {
  id: string;
  name: string;
  /** SkillChannel binding id used by platform/web chat APIs. */
  channelId: string;
  skillId?: string;
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
  return rows
    .map((item) => {
      const id = String(item.id ?? item.channel_id ?? '');
      const channelId = String(item.channel_id ?? item.id ?? '');
      const name =
        String(item.app_name ?? item.skill_name ?? item.name ?? '').trim() ||
        (id ? `渠道 ${id}` : '');
      const skillId =
        item.skill_id === undefined || item.skill_id === null ? undefined : String(item.skill_id);
      return { id, name, channelId, skillId };
    })
    .filter((item) => item.id && item.channelId);
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
      return {
        id: String(item.id ?? `history_${index}`),
        type: 'text' as const,
        content: extractMessageText(item.conversation_content ?? item.content),
        sender: role,
        timestamp,
      };
    })
    .filter((item) => String(item.content).trim() !== '');
}

export function lastSessionStorageKey(prefix: string, userId: string, teamId: string): string {
  return `${prefix}:${userId}:${teamId}`;
}

export function dockCollapsedStorageKey(prefix: string, userId: string, teamId: string): string {
  return `${prefix}:collapsed:${userId}:${teamId}`;
}

/** Missing key or unreadable storage means collapsed (open when needed). */
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
  const sessionId = sessions.some((item) => item.id === stored?.sessionId)
    ? stored!.sessionId
    : sessions[0]?.id ?? null;
  return { app, sessionId };
}

export function createPlatformSessionId(): string {
  return `session_${Date.now()}`;
}

export function isRequiredPlatformContract(
  platform: PlatformContract | undefined
): platform is PlatformContract {
  return isPlatformMode({ platform });
}
