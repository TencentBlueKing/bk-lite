/**
 * 识别误入正文的 DeepAgent 规划载荷，避免 CUSTOM 事件被当成聊天气泡。
 */

export type PlannedExecutionKind = 'status' | 'step';

const STATUS_PHASES = new Set(['planning', 'planned', 'replanning', 'idle']);
const STEP_PHASES = new Set(['start', 'end']);

export const tryParseJsonValue = (raw: string): unknown => {
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
};

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const unwrapCustomValue = (value: unknown): unknown => {
  if (typeof value === 'string') {
    const parsed = tryParseJsonValue(value);
    return parsed == null ? value : unwrapCustomValue(parsed);
  }
  if (!isRecord(value)) {
    return value;
  }
  if (isRecord(value.data) && looksLikePlannedExecutionPayload(value.data)) {
    return value.data;
  }
  if (isRecord(value.value) && looksLikePlannedExecutionPayload(value.value)) {
    return value.value;
  }
  return value;
};

export const looksLikePlannedExecutionPayload = (value: unknown): PlannedExecutionKind | null => {
  const payload = unwrapCustomValue(value);
  if (!isRecord(payload)) {
    return null;
  }
  const phase = typeof payload.phase === 'string' ? payload.phase : '';
  if (STATUS_PHASES.has(phase) && payload.step_index == null) {
    return 'status';
  }
  if (STEP_PHASES.has(phase) && (payload.step_index != null || payload.objective != null || Array.isArray(payload.tools))) {
    return 'step';
  }
  return null;
};

export const plannedExecutionKindFromText = (raw: string): PlannedExecutionKind | null => {
  return looksLikePlannedExecutionPayload(tryParseJsonValue(raw));
};

const extractTopLevelObjects = (value: string): string[] => {
  const objects: string[] = [];
  let depth = 0;
  let start = -1;
  let inString = false;
  let escaped = false;
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
    if (ch === '"') {
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (ch === '{') {
      if (depth === 0) start = i;
      depth += 1;
      continue;
    }
    if (ch === '}' && depth > 0) {
      depth -= 1;
      if (depth === 0 && start >= 0) {
        objects.push(value.slice(start, i + 1));
        start = -1;
      }
    }
  }
  return objects;
};

/** 从 Markdown 正文里剔除误入的规划 JSON，只留下最终回答。 */
export const stripPlannedExecutionDumps = (content: string): string => {
  if (!content) return '';
  let result = content.replace(/^\s*planned_execution_(?:status|step)\s+/gm, '');
  for (const slice of extractTopLevelObjects(result)) {
    if (looksLikePlannedExecutionPayload(tryParseJsonValue(slice))) {
      result = result.replace(slice, '');
    }
  }
  return result.replace(/\n{3,}/g, '\n\n').trim();
};
