interface EventRawRecord {
  raw_data?: unknown;
  enrichment?: unknown;
}

export function presentEventRawData(record: EventRawRecord): unknown {
  const raw = record.raw_data;
  const enrichment = record.enrichment ?? {};
  if (raw == null) {
    return record;
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return { raw_data: raw, enrichment };
  }
  return {
    ...(raw as Record<string, unknown>),
    enrichment,
  };
}
