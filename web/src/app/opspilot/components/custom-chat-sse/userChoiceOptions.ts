import { UserChoiceOption, UserChoiceRequest } from '../../types/global';

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function normalizeUserChoiceOptions(options: unknown): UserChoiceOption[] {
  if (!Array.isArray(options)) {
    return [];
  }
  const normalized: UserChoiceOption[] = [];
  const seen = new Set<string>();
  for (const item of options) {
    if (typeof item === 'string') {
      const key = item.trim();
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      normalized.push({ key, label: key });
      continue;
    }
    if (!item || typeof item !== 'object') {
      continue;
    }
    const record = item as Record<string, unknown>;
    const key = asText(record.key) || asText(record.value) || asText(record.name);
    const label = asText(record.label) || asText(record.display_name) || key;
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    normalized.push({
      key,
      label,
      description: asText(record.description) || undefined,
      icon: asText(record.icon) || undefined,
      disabled: Boolean(record.disabled),
      recommended: Boolean(record.recommended),
    });
  }
  return normalized;
}

export function isUserChoiceRequestClosed(
  status: UserChoiceRequest['status'] | undefined,
): boolean {
  return status === 'submitted' || status === 'timeout';
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 从历史里的「问题 + 编号选项」还原选择卡。至少两项才算选择题。 */
export function choiceRequestFromVisibleText(content: string): UserChoiceRequest | null {
  const lines = String(content || '').split(/\r?\n/);
  let start = -1;
  const labels: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].trim().match(/^\d+[.、]\s+(.+)$/);
    if (!match) {
      if (labels.length >= 2) break;
      start = -1;
      labels.length = 0;
      continue;
    }
    if (start < 0) start = index;
    labels.push(match[1].trim());
  }
  if (labels.length < 2 || start < 0) return null;
  let title = '';
  for (let index = start - 1; index >= 0; index -= 1) {
    const line = lines[index].trim();
    if (!line) continue;
    title = line;
    break;
  }
  if (!title || !/[?？]/.test(title) && !title.includes('请选择') && !title.includes('请确认')) return null;
  const options = labels.map((label) => ({ key: label, label }));
  let hash = 0;
  const seed = `${title}\n${labels.join('\n')}`;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) | 0;
  }
  return {
    execution_id: '',
    node_id: '',
    choice_id: `history-${Math.abs(hash).toString(36)}`,
    title,
    options,
    multiple: false,
    min_select: 1,
    max_select: 1,
    timeout_seconds: 0,
    default_keys: [],
    display_hint: 'auto',
    received_at: 0,
    status: 'pending',
  };
}
export function stripChoicePromptFromContent(
  content: string,
  requests: UserChoiceRequest[] | undefined,
): string {
  if (!content || !requests?.length) {
    return content || '';
  }
  let text = content;
  for (const request of requests) {
    const options = normalizeUserChoiceOptions(request.options);
    const labels = options.map((option) => option.label).filter(Boolean);
    if (!labels.length) {
      continue;
    }
    const title = (request.title || '').trim();
    const numbered = labels.map((label) => `\\d+[.、]\\s*${escapeRegExp(label)}`).join('\\s*\\n\\s*');
    const titlePart = title ? `${escapeRegExp(title)}\\s*\\n+\\s*` : '';
    text = text.replace(new RegExp(`${titlePart}${numbered}`, 'g'), '');
  }
  return text.replace(/\n{3,}/g, '\n\n').trim();
}

interface ChoiceMessage {
  role: string;
  content?: string;
  userChoiceRequests?: UserChoiceRequest[];
}

export function applyAnsweredUserChoices<T extends ChoiceMessage>(messages: T[]): T[] {
  return messages.map((message, index) => {
    const cards = message.userChoiceRequests;
    if (!cards?.length) {
      return message;
    }
    const laterUser = messages.slice(index + 1).find((item) => item.role === 'user' && String(item.content || '').trim());
    if (!laterUser) {
      return message;
    }
    const text = String(laterUser.content).trim();
    return {
      ...message,
      userChoiceRequests: cards.map((card) => {
        const options = normalizeUserChoiceOptions(card.options);
        const match = options.find((option) => option.label === text || option.key === text);
        if (match) {
          return {
            ...card,
            status: 'submitted' as const,
            selected: [match.key],
          };
        }
        if (card.status === 'submitted' && card.selected && card.selected.length > 0) {
          return { ...card, status: 'submitted' as const };
        }
        return {
          ...card,
          status: 'submitted' as const,
          selected: [],
        };
      }),
    };
  });
}
