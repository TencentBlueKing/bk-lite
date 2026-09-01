const AGUI_TEXT_EVENT_TYPES = new Set([
  'TEXT_MESSAGE_CONTENT',
  'TEXT_MESSAGE_CHUNK',
]);

const SKIP_CUSTOM_EVENTS = new Set([
  'agent_step_progress',
  'sub_agent_progress',
  'browser_step_progress',
  'browser_task_received',
  'planned_execution_step',
  'planned_execution_status',
  'skill_view',
  'wiki_citations',
  'user_choice_result',
  'assistant_text_retract',
  'stream_keepalive',
  'llm_context_usage',
]);

/**
 * 进度/元数据类 CUSTOM 事件：只描述执行过程，不该作为聊天气泡展示。
 * 实时流与历史回放共用同一份清单，避免规划 JSON 被降级成正文。
 */
export function isSilentCustomEvent(name: string): boolean {
  return SKIP_CUSTOM_EVENTS.has(name);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function looksLikeAguiEventType(type: string): boolean {
  return (
    type.startsWith('TEXT_MESSAGE_') ||
    type.startsWith('TOOL_CALL_') ||
    type.startsWith('RUN_') ||
    type === 'CUSTOM' ||
    type === 'THINKING' ||
    type === 'THINKING_START' ||
    type === 'THINKING_END'
  );
}

function looksLikeAguiPayload(raw: string): boolean {
  return (
    looksLikeAguiEventType(raw) ||
    raw.includes('TEXT_MESSAGE_') ||
    raw.includes('RUN_STARTED') ||
    raw.includes('TOOL_CALL_') ||
    raw.includes("'type':") ||
    raw.includes('"type":')
  );
}

function escapeNewlinesInStrings(raw: string): string {
  let result = '';
  let inSingle = false;
  let inDouble = false;
  let escaped = false;

  for (let i = 0; i < raw.length; i += 1) {
    const ch = raw[i];
    if (escaped) {
      result += ch;
      escaped = false;
      continue;
    }
    if (ch === '\\') {
      result += ch;
      escaped = true;
      continue;
    }
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      result += ch;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      result += ch;
      continue;
    }
    if ((ch === '\n' || ch === '\r') && (inSingle || inDouble)) {
      result += ch === '\n' ? '\\n' : '\\r';
      continue;
    }
    result += ch;
  }
  return result;
}

function normalizePythonJson(raw: string): string {
  const escapedRaw = escapeNewlinesInStrings(raw);
  let result = '';
  let inSingle = false;
  let inDouble = false;
  let escaped = false;
  let token = '';

  const flushToken = () => {
    if (!token) return;
    if (!inSingle && !inDouble) {
      if (token === 'None') result += 'null';
      else if (token === 'True') result += 'true';
      else if (token === 'False') result += 'false';
      else result += token;
    } else {
      result += token;
    }
    token = '';
  };

  for (let i = 0; i < escapedRaw.length; i += 1) {
    const ch = escapedRaw[i];
    if (inSingle || inDouble) {
      if (escaped) {
        result += ch;
        escaped = false;
        continue;
      }
      if (ch === '\\') {
        result += ch;
        escaped = true;
        continue;
      }
      if (inSingle && ch === "'") {
        result += '"';
        inSingle = false;
        continue;
      }
      if (inDouble && ch === '"') {
        result += '"';
        inDouble = false;
        continue;
      }
      if (ch === '\n') {
        result += '\\n';
        continue;
      }
      if (inSingle && ch === '"') {
        result += '\\"';
        continue;
      }
      result += ch;
      continue;
    }
    if (ch === "'") {
      flushToken();
      inSingle = true;
      result += '"';
      continue;
    }
    if (ch === '"') {
      flushToken();
      inDouble = true;
      result += '"';
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      token += ch;
      continue;
    }
    flushToken();
    result += ch;
  }
  flushToken();
  return result;
}

function splitTopLevelObjects(value: string): string[] {
  const objects: string[] = [];
  let inSingle = false;
  let inDouble = false;
  let escaped = false;
  let depth = 0;
  let startIndex = -1;

  for (let i = 0; i < value.length; i += 1) {
    const ch = value[i];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (ch === '\\') {
      escaped = true;
      continue;
    }
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      continue;
    }
    if (inSingle || inDouble) continue;
    if (ch === '{') {
      if (depth === 0) startIndex = i;
      depth += 1;
      continue;
    }
    if (ch === '}') {
      depth -= 1;
      if (depth === 0 && startIndex >= 0) {
        objects.push(value.slice(startIndex, i + 1));
        startIndex = -1;
      }
    }
  }
  return objects;
}

function parseJsonValue(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    try {
      return JSON.parse(normalizePythonJson(raw));
    } catch {
      return null;
    }
  }
}

function parseAguiEvents(raw: string): Record<string, unknown>[] | null {
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  const direct = parseJsonValue(trimmed);
  if (Array.isArray(direct)) {
    return direct.filter(isRecord);
  }
  if (isRecord(direct) && typeof direct.type === 'string') {
    return [direct];
  }
  const slices = splitTopLevelObjects(trimmed);
  if (slices.length === 0) {
    return null;
  }
  const parsed = slices.map(parseJsonValue).filter(isRecord);
  return parsed.length > 0 ? parsed : null;
}

function customEventText(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (!isRecord(value)) {
    return '';
  }
  if (typeof value.markdown === 'string') return value.markdown;
  if (typeof value.content === 'string') return value.content;
  if (typeof value.description === 'string') return value.description;
  if (typeof value.title === 'string') return value.title;
  return '';
}

function assembleThinkingFromEvents(events: Record<string, unknown>[]): string {
  let thinking = '';
  for (const event of events) {
    const type = event.type;
    if (
      (type === 'THINKING' || type === 'THINKING_TEXT_MESSAGE_CONTENT') &&
      event.delta != null
    ) {
      thinking += String(event.delta);
    }
  }
  return thinking;
}

function assembleTextFromEvents(events: Record<string, unknown>[]): string {
  let text = '';
  for (const event of events) {
    const type = event.type;
    if (typeof type !== 'string') {
      continue;
    }
    if (AGUI_TEXT_EVENT_TYPES.has(type) && event.delta != null) {
      text += String(event.delta);
      continue;
    }
    if (type === 'CUSTOM') {
      if (typeof event.name === 'string' && SKIP_CUSTOM_EVENTS.has(event.name)) {
        continue;
      }
      const custom = customEventText(event.value);
      if (custom) {
        text += (text && !text.endsWith('\n') ? '\n' : '') + custom;
      }
    }
  }
  return text.trim();
}

function eventsFromUnknown(content: unknown): Record<string, unknown>[] | null {
  if (typeof content === 'string') {
    if (!looksLikeAguiPayload(content)) {
      return null;
    }
    return parseAguiEvents(content);
  }
  if (Array.isArray(content)) {
    const records = content.filter(isRecord);
    if (records.some((item) => typeof item.type === 'string' && looksLikeAguiEventType(item.type))) {
      return records;
    }
    return null;
  }
  if (isRecord(content) && typeof content.type === 'string' && looksLikeAguiEventType(content.type)) {
    return [content];
  }
  return null;
}

/** Collapse stored AG-UI event dumps into readable assistant text and thinking. */
export function assembleAguiHistoryParts(
  content: unknown
): { text: string; thinking: string } | null {
  const events = eventsFromUnknown(content);
  if (!events || events.length === 0) {
    return null;
  }
  return {
    text: assembleTextFromEvents(events),
    thinking: assembleThinkingFromEvents(events),
  };
}

/** Collapse stored AG-UI event dumps into readable assistant text. */
export function assembleAguiHistoryText(content: unknown): string | null {
  const parts = assembleAguiHistoryParts(content);
  return parts ? parts.text : null;
}
