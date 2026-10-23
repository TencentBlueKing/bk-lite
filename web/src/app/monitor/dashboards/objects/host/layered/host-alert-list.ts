/** 概览告警抽屉与 KPI 计数共用的活跃告警查询。只查当前实例，不放宽到全租户。 */
export const HOST_ALERT_PAGE_SIZE = 50;

/** 概览事件轨原来的条数。计数与事件同一次请求，不再另打 page_size=1。 */
export const HOST_OVERVIEW_ALERT_PAGE_SIZE = 20;

export const activeHostAlertParams = (
  instanceId: string,
  page: number,
  pageSize: number
) => ({
  monitor_instance_id: instanceId,
  status_in: 'new' as unknown as string[],
  page,
  page_size: pageSize
});

/**
 * 概览只打这一次：KPI 用 count，事件轨用 results。
 * status_in 与抽屉活跃口径一致，计数不会混入已恢复/关闭。
 * 因此轨上只会出现仍为 new 的告警。
 */
export const overviewHostAlertParams = (instanceId: string) => (
  activeHostAlertParams(instanceId, 1, HOST_OVERVIEW_ALERT_PAGE_SIZE)
);

export interface HostAlertRecord {
  id: string | number;
  level: string;
  content: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  start_event_time?: string | null;
  end_event_time?: string | null;
  policy?: { name?: string | null } | null;
}

const LEVEL_RANK: Record<string, number> = {
  critical: 0,
  error: 1,
  warning: 2
};

const textField = (value: unknown) => (typeof value === 'string' ? value : '');

export const hostAlertRecency = (row: HostAlertRecord) => {
  const raw = row.updated_at || row.end_event_time || row.created_at || row.start_event_time || '';
  const time = Date.parse(String(raw));
  return Number.isFinite(time) ? time : 0;
};

/** 高严重度在前；同级较新的在前。未知级别沉底。 */
export const compareHostAlerts = (left: HostAlertRecord, right: HostAlertRecord) => {
  const rankDelta = (LEVEL_RANK[left.level] ?? 99) - (LEVEL_RANK[right.level] ?? 99);
  if (rankDelta !== 0) return rankDelta;
  return hostAlertRecency(right) - hostAlertRecency(left);
};

export const sortHostAlerts = (rows: HostAlertRecord[]) => [...rows].sort(compareHostAlerts);

export const normalizeHostAlerts = (results: unknown): HostAlertRecord[] => {
  if (!Array.isArray(results)) return [];
  const rows: HostAlertRecord[] = [];
  for (const item of results) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    if (row.id == null || row.id === '') continue;
    const policyRaw = row.policy;
    const policy = policyRaw && typeof policyRaw === 'object'
      ? { name: textField((policyRaw as { name?: unknown }).name) }
      : null;
    rows.push({
      id: row.id as string | number,
      level: textField(row.level),
      content: textField(row.content),
      status: textField(row.status),
      created_at: textField(row.created_at) || undefined,
      updated_at: textField(row.updated_at) || undefined,
      start_event_time: textField(row.start_event_time) || null,
      end_event_time: textField(row.end_event_time) || null,
      policy
    });
  }
  return rows;
};

export const mergeHostAlerts = (current: HostAlertRecord[], incoming: HostAlertRecord[]) => {
  const seen = new Set(current.map((row) => String(row.id)));
  const next = [...current];
  for (const row of incoming) {
    const key = String(row.id);
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(row);
  }
  return sortHostAlerts(next);
};

export const readAlertCount = (payload: { count?: unknown } | null | undefined, fallback: number) => (
  typeof payload?.count === 'number' ? payload.count : fallback
);

export const isCanceledRequest = (error: unknown) => {
  if (!error || typeof error !== 'object') return false;
  const name = 'name' in error ? String(error.name) : '';
  const code = 'code' in error ? String(error.code) : '';
  return name === 'CanceledError' || name === 'AbortError' || code === 'ERR_CANCELED';
};
