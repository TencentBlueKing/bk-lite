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
