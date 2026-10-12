/**
 * 监控走查本地 Mock。
 * 仅在 development 且 NEXT_PUBLIC_MONITOR_UI_DEMO=true 时，
 * 后端列表为空或接口失败才注入，用于刷 UI 时看见状态徽章和表格行。
 */

const DEMO_NOW = '2026-10-12T08:27:00.000Z';

export const isMonitorUiDemoEnabled = () =>
  process.env.NODE_ENV === 'development' &&
  process.env.NEXT_PUBLIC_MONITOR_UI_DEMO === 'true';

export const isCanceledRequest = (error: unknown) => {
  if (!error || typeof error !== 'object') return false;
  const err = error as { code?: string; name?: string };
  return (
    err.code === 'ERR_CANCELED' ||
    err.name === 'CanceledError' ||
    err.name === 'AbortError'
  );
};

const asObjectId = (value: unknown) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 29;
};

const matchKeyword = (value: unknown, keyword?: string) => {
  const needle = String(keyword || '').trim().toLowerCase();
  if (!needle) return true;
  return String(value || '').toLowerCase().includes(needle);
};

export const demoMonitorPolicies = (params: {
  monitor_object_id?: unknown;
  name?: string;
} = {}) => {
  const monitorObject = asObjectId(params.monitor_object_id);
  const rows = [
    {
      id: 900001,
      name: '设计走查-CPU过高',
      monitor_object: monitorObject,
      source: { type: 'instance', values: ["('prod-web-01',)", "('prod-web-02',)"] },
      created_by: 'admin',
      created_at: DEMO_NOW,
      last_run_time: DEMO_NOW,
      enable: true,
      permission: ['View', 'Edit', 'Delete'],
    },
    {
      id: 900002,
      name: '设计走查-内存过高',
      monitor_object: monitorObject,
      source: { type: 'instance', values: ["('prod-db-01',)"] },
      created_by: 'admin',
      created_at: DEMO_NOW,
      last_run_time: null,
      enable: false,
      permission: ['View', 'Edit', 'Delete'],
    },
    {
      id: 900003,
      name: '设计走查-磁盘将满',
      monitor_object: monitorObject,
      source: { type: 'instance', values: [] },
      created_by: 'admin',
      created_at: DEMO_NOW,
      last_run_time: DEMO_NOW,
      enable: true,
      permission: ['View', 'Edit'],
    },
  ];
  const items = rows.filter((row) => matchKeyword(row.name, params.name));
  return { items, count: items.length };
};

export const demoMonitorAlerts = (
  params: Record<string, unknown> = {}
) => {
  const monitorObject = asObjectId(
    params.monitor_object_id === 'all' ? 29 : params.monitor_object_id
  );
  const rows = [
    {
      id: 900101,
      level: 'critical',
      content: '设计走查-CPU过高',
      alert_type: 'alert',
      monitor_instance_name: 'prod-web-01',
      status: 'new',
      updated_at: DEMO_NOW,
      created_at: DEMO_NOW,
      handlers: ['admin'],
      handlers_display: ['admin'],
      policy: { monitor_object: monitorObject, notice: true },
    },
    {
      id: 900102,
      level: 'warning',
      content: '设计走查-内存过高',
      alert_type: 'alert',
      monitor_instance_name: 'prod-web-02',
      status: 'new',
      updated_at: DEMO_NOW,
      created_at: DEMO_NOW,
      handlers: [],
      handlers_display: [],
      policy: { monitor_object: monitorObject, notice: false },
    },
    {
      id: 900103,
      level: 'error',
      content: '设计走查-采集失败',
      alert_type: 'no_data',
      monitor_instance_name: 'prod-db-01',
      status: 'closed',
      updated_at: DEMO_NOW,
      created_at: DEMO_NOW,
      handlers: ['admin'],
      handlers_display: ['admin'],
      policy: { monitor_object: monitorObject, notice: true },
    },
    {
      id: 900104,
      level: 'warning',
      content: '设计走查-磁盘将满',
      alert_type: 'alert',
      monitor_instance_name: 'mysql-01',
      status: 'recovered',
      updated_at: DEMO_NOW,
      created_at: DEMO_NOW,
      handlers: [],
      handlers_display: [],
      policy: { monitor_object: monitorObject, notice: false },
    },
  ];

  const statusIn = String(params.status_in || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const levelIn = String(params.level_in || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const mine = params.my_alert === 1 || params.my_alert === '1';

  const filtered = rows.filter((row) => {
    if (statusIn.length && !statusIn.includes(row.status)) return false;
    if (levelIn.length && !levelIn.includes(row.level)) return false;
    if (!matchKeyword(row.content, params.content as string | undefined)) return false;
    if (mine && !(row.handlers || []).includes('admin')) return false;
    return true;
  });

  return { results: filtered, count: filtered.length };
};

export const demoPolicyGroups = (params: {
  monitor_object_id?: unknown;
  name?: string;
  create_default?: boolean;
} = {}) => {
  const rows = [
    {
      id: 900201,
      name: '设计走查-主机默认组',
      is_default: true,
      member_count: 3,
      enable: true,
      enable_uniform: true,
      notice: true,
      rules: [
        {
          id: 9101,
          name: 'CPU过高',
          plugin_name: 'Host',
          threshold: [{ level: 'critical', method: '>', value: 90 }],
        },
        {
          id: 9102,
          name: '内存过高',
          plugin_name: 'Host',
          threshold: [{ level: 'warning', method: '>', value: 80 }],
        },
      ],
    },
    {
      id: 900202,
      name: '设计走查-核心主机组',
      is_default: false,
      member_count: 2,
      enable: false,
      enable_uniform: false,
      notice: false,
      rules: [
        {
          id: 9103,
          name: '磁盘将满',
          plugin_name: 'Host',
          threshold: [{ level: 'warning', method: '>', value: 85 }],
        },
      ],
    },
  ].filter((row) => matchKeyword(row.name, params.name));

  if (params.create_default === false) return rows;
  return { items: rows, count: rows.length };
};

export const demoPolicyGroupMembers = () => [
  {
    instance_id: "('prod-web-01',)",
    name: 'prod-web-01',
    state: 'member',
    legacy_policies: [{ id: 900001, name: '设计走查-CPU过高', enable: true }],
  },
  {
    instance_id: "('prod-web-02',)",
    name: 'prod-web-02',
    state: 'declined',
    legacy_policies: [],
  },
  {
    instance_id: "('prod-db-01',)",
    name: 'prod-db-01',
    state: 'skipped',
    legacy_policies: [{ id: 900002, name: '设计走查-内存过高', enable: false }],
  },
];

const hasListRows = (data: unknown) => {
  if (Array.isArray(data)) return data.length > 0;
  if (!data || typeof data !== 'object') return false;
  const payload = data as { items?: unknown[]; results?: unknown[] };
  if (Array.isArray(payload.items)) return payload.items.length > 0;
  if (Array.isArray(payload.results)) return payload.results.length > 0;
  return false;
};

export async function withMonitorUiDemoFallback<T>(
  run: () => Promise<T>,
  fallback: () => T
): Promise<T> {
  try {
    const data = await run();
    if (!isMonitorUiDemoEnabled() || hasListRows(data)) return data;
    return fallback();
  } catch (error) {
    if (!isMonitorUiDemoEnabled() || isCanceledRequest(error)) throw error;
    return fallback();
  }
}
