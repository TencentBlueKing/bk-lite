import { v4 as uuidv4 } from 'uuid';
import type { IntegrationMonitoredObject } from '@/app/monitor/types/integration';

const HOST_FIELDS = ['ip', 'host', 'ENV_HOST'] as const;
const PORT_FIELDS = ['port', 'ENV_PORT'] as const;
const ENDPOINT_FIELDS = ['url', 'server', 'server_url', 'endpoint', 'jmx_url', 'ENV_KAFKA_SERVER'] as const;
const AGENT_TARGET_KEYS = new Set<string>([
  ...HOST_FIELDS,
  ...ENDPOINT_FIELDS,
]);

export interface CmdbDraftTableColumn {
  name?: string;
  widget_props?: { placeholder?: string; placeholder_en?: string };
}

const asText = (value: unknown) =>
  typeof value === 'string' ? value.trim() : value == null || value === '' ? '' : String(value).trim();

const asGroupIds = (value: unknown, fallback: Array<string | number>) => {
  if (Array.isArray(value) && value.length) {
    return value.map((item) => String(item));
  }
  return fallback.map((item) => String(item));
};

export const collectIps = (value: unknown): string[] => {
  const raw = Array.isArray(value) ? value : [value];
  const ips: string[] = [];
  for (const item of raw) {
    const text = asText(item);
    if (!text) continue;
    for (const part of text.split(/[,;]+/)) {
      const ip = part.trim();
      if (ip) ips.push(ip);
    }
  }
  return ips;
};

const hasNodeIds = (value: IntegrationMonitoredObject['node_ids']) => {
  if (Array.isArray(value)) return value.some((item) => asText(item));
  return Boolean(asText(value));
};

const fillIfEmpty = (
  next: IntegrationMonitoredObject,
  initItems: Record<string, unknown>,
  field: string,
  value: string,
) => {
  if (!value) return;
  if (Object.prototype.hasOwnProperty.call(initItems, field) && !asText(next[field])) {
    next[field] = value;
  }
};

const columnPlaceholder = (column?: CmdbDraftTableColumn) =>
  asText(column?.widget_props?.placeholder) || asText(column?.widget_props?.placeholder_en);

const endpointValue = (placeholder: string, ip: string, port: string) => {
  if (!ip) return '';
  const hostPort = port ? `${ip}:${port}` : ip;
  if (/^https?:\/\//i.test(placeholder)) return `http://${hostPort}`;
  return hostPort;
};

export const isHostAgentTable = (initItems: Record<string, unknown>) =>
  Object.prototype.hasOwnProperty.call(initItems, 'node_ids') &&
  !Object.keys(initItems).some((key) => AGENT_TARGET_KEYS.has(key));

export const matchNodeIdByIp = (
  ipValue: unknown,
  nodes: Array<{ id?: string | number; value?: string | number; ip?: string; disabled?: boolean }>,
): string | undefined => {
  const wanted = new Set(collectIps(ipValue));
  if (!wanted.size) return undefined;
  const matches = nodes.filter((node) => wanted.has(asText(node.ip)));
  if (!matches.length) return undefined;
  const usable = matches.find((node) => !node.disabled) || matches[0];
  const id = asText(usable.value) || asText(usable.id);
  return id || undefined;
};

export const projectCmdbDraftRowOntoTable = (
  row: IntegrationMonitoredObject,
  initItems: Record<string, unknown>,
  columns: CmdbDraftTableColumn[] = [],
): IntegrationMonitoredObject => {
  const next: IntegrationMonitoredObject = {
    ...initItems,
    ...row,
    key: row.key || uuidv4(),
  };
  const ip = collectIps(row.ip)[0] || '';
  const port = asText(row.port);
  const byName = new Map(columns.map((column) => [column.name, column]));

  for (const field of HOST_FIELDS) {
    fillIfEmpty(next, initItems, field, ip);
  }
  for (const field of PORT_FIELDS) {
    fillIfEmpty(next, initItems, field, port);
  }
  for (const field of ENDPOINT_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(initItems, field)) continue;
    const seeded = endpointValue(columnPlaceholder(byName.get(field)), ip, port);
    fillIfEmpty(next, initItems, field, seeded);
  }
  if (!asText(next.ip) && ip) next.ip = ip;
  if (!asText(next.port) && port) next.port = port;
  return next;
};

export const applyCmdbDraftNodeMatch = <T extends IntegrationMonitoredObject>(
  rows: T[],
  nodes: Array<{ id?: string | number; value?: string | number; ip?: string; disabled?: boolean }>,
  matchByIp = true,
): T[] => {
  if (!matchByIp || !rows.length || !nodes.length) return rows;
  let changed = false;
  const next = rows.map((row) => {
    if (!asText(row.cmdb_id) || hasNodeIds(row.node_ids)) return row;
    const nodeId = matchNodeIdByIp(row.ip || row.host, nodes);
    if (!nodeId) return row;
    changed = true;
    return { ...row, node_ids: nodeId };
  });
  return changed ? next : rows;
};

export const mapCmdbAccessDraftRows = (
  rows: unknown,
  fallbackGroupIds: Array<string | number> = [],
): IntegrationMonitoredObject[] => {
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => row && typeof row === 'object' && !Array.isArray(row))
    .map((row) => {
      const item = row as Record<string, unknown>;
      const instanceName = asText(item.instance_name) || asText(item.inst_name);
      const cmdbId = asText(item.cmdb_id) || asText(item.inst_uuid);
      const ip = collectIps(item.ip)[0] || '';
      const port = asText(item.port);
      return {
        key: uuidv4(),
        instance_name: instanceName || undefined,
        ip: ip || undefined,
        port: port || undefined,
        group_ids: asGroupIds(item.group_ids ?? item.organization, fallbackGroupIds),
        cmdb_id: cmdbId || undefined,
        cloud_region_id: item.cloud_region_id ?? undefined,
      };
    });
};
