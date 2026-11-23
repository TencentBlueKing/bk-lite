interface EventRawRecord {
  raw_data?: unknown;
  enrichment?: unknown;
  assignee?: unknown;
}

export function presentEventRawData(record: EventRawRecord): unknown {
  const raw = record.raw_data;
  const enrichment = record.enrichment ?? {};
  const assignee = Array.isArray(record.assignee) ? record.assignee : [];
  if (raw == null) {
    return record;
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return { raw_data: raw, enrichment, assignee };
  }
  return {
    ...(raw as Record<string, unknown>),
    enrichment,
    assignee,
  };
}

const SHIELD_REPLAY_PREFIX = 'shield-replay:';

export function shieldReplaySourceEventId(raw: unknown): string | null {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }
  const generation = (raw as Record<string, unknown>).lifecycle_generation;
  if (typeof generation !== 'string' || !generation.startsWith(SHIELD_REPLAY_PREFIX)) {
    return null;
  }
  const sourceEventId = generation.slice(SHIELD_REPLAY_PREFIX.length).trim();
  return sourceEventId || null;
}

