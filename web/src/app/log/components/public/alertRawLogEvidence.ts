export interface FrozenQueryClue {
  policy_id?: number | string | null;
  policy_name?: string | null;
  collect_type_id?: number | string | null;
  collect_type_name?: string | null;
  log_groups?: unknown;
  alert_type?: string | null;
  alert_name?: string | null;
  alert_level?: string | null;
  alert_condition?: unknown;
  period?: unknown;
  schedule?: unknown;
  show_fields?: unknown;
  window_start?: number | string | null;
  window_end?: number | string | null;
}

export interface AlertSnapshotItem {
  type?: string;
  event_id?: string;
  event_time?: string;
  snapshot_time?: string;
  raw_data?: unknown;
  query_clue?: FrozenQueryClue | null;
}

export interface AlertInfoEvidence {
  id?: string;
  source_id?: string;
  level?: string;
  content?: string;
  start_event_time?: string;
}

export function hasFrozenQueryClue(clue: unknown): clue is FrozenQueryClue {
  return Boolean(clue) && typeof clue === 'object' && !Array.isArray(clue) && Object.keys(clue as object).length > 0;
}

export function hasSnapshotRawData(rawData: unknown): boolean {
  if (rawData == null) return false;
  if (Array.isArray(rawData)) return rawData.length > 0;
  if (typeof rawData === 'object') return Object.keys(rawData).length > 0;
  return true;
}

export function historicalAlertInfo(alertInfo: AlertInfoEvidence | null | undefined): AlertInfoEvidence {
  if (!alertInfo) return {};
  return {
    id: alertInfo.id,
    source_id: alertInfo.source_id,
    level: alertInfo.level,
    content: alertInfo.content,
    start_event_time: alertInfo.start_event_time,
  };
}
