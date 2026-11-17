export const CONTEXT_USAGE_EVENT = 'llm_context_usage';

export const CONTEXT_USAGE_SEGMENT_IDS = [
  'system',
  'tools',
  'skills',
  'wiki',
  'summary',
  'conversation',
] as const;

export type ContextUsageSegmentId = (typeof CONTEXT_USAGE_SEGMENT_IDS)[number];

export interface ContextUsageSegment {
  id: ContextUsageSegmentId;
  tokens: number;
}

export interface LlmContextUsage {
  packetTokens: number;
  inputWorkingTokens: number;
  windowTokens: number;
  compactionThresholdTokens: number;
  compacted: boolean;
  segments: ContextUsageSegment[];
}

const SEGMENT_ID_SET = new Set<string>(CONTEXT_USAGE_SEGMENT_IDS);

function asInt(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.floor(value));
}

export function parseLlmContextUsage(raw: unknown): LlmContextUsage | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const inputWorkingTokens = asInt(record.input_working_tokens);
  const packetTokens = asInt(record.packet_tokens);
  if (inputWorkingTokens <= 0 || packetTokens <= 0) {
    return null;
  }
  const segments: ContextUsageSegment[] = [];
  if (Array.isArray(record.segments)) {
    for (const item of record.segments) {
      if (!item || typeof item !== 'object') {
        continue;
      }
      const row = item as Record<string, unknown>;
      const id = typeof row.id === 'string' ? row.id : '';
      const tokens = asInt(row.tokens);
      if (!SEGMENT_ID_SET.has(id) || tokens <= 0) {
        continue;
      }
      segments.push({ id: id as ContextUsageSegmentId, tokens });
    }
  }
  return {
    packetTokens,
    inputWorkingTokens,
    windowTokens: asInt(record.window_tokens),
    compactionThresholdTokens: asInt(record.compaction_threshold_tokens),
    compacted: record.compacted === true,
    segments,
  };
}

export function formatContextTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    const millions = tokens / 1_000_000;
    return `${millions >= 10 || millions % 1 === 0 ? millions.toFixed(0) : millions.toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    const thousands = tokens / 1_000;
    return `${thousands >= 10 || thousands % 1 === 0 ? thousands.toFixed(0) : thousands.toFixed(1)}K`;
  }
  return String(tokens);
}

export function contextUsagePercent(usage: LlmContextUsage): number {
  if (usage.inputWorkingTokens <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((usage.packetTokens / usage.inputWorkingTokens) * 100));
}

export function parseLlmContextUsageFromEnvelope(payload: unknown): LlmContextUsage | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }
  return parseLlmContextUsage((payload as Record<string, unknown>).llm_context_usage);
}
