import type { ChangeRecord } from './changeRecordTypes';

export const SCENARIO_COLORS: Record<
  string,
  { dot: string; bg: string; text: string }
> = {
  ordinary_attribute_change: {
    dot: '#155AEF',
    bg: '#e1edfc',
    text: '#155AEF',
  },
  relation_change: { dot: '#F04438', bg: '#FEE4E2', text: '#D92D20' },
  device_lifecycle: { dot: '#12B76A', bg: '#D1FADF', text: '#039855' },
  collect_automation_change: {
    dot: '#F79009',
    bg: '#FEF0C7',
    text: '#DC6803',
  },
  model_management_change: { dot: '#7A5AF8', bg: '#EBE9FE', text: '#6938EF' },
  custom_reporting_change: { dot: '#06AED4', bg: '#CFF9FE', text: '#0E7090' },
};

export const DEFAULT_SCENARIOS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
];

export const STAT_KEYS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
  'collect_automation_change',
  'custom_reporting_change',
];

export interface ChangeRecordMonthGroup {
  month: string;
  list: ChangeRecord[];
  count: number;
}

export function filterChangeRecordsByScenarios(
  records: ChangeRecord[],
  scenarios: readonly string[],
): ChangeRecord[] {
  if (!scenarios.length) return records;
  return records.filter((item) => scenarios.includes(item.scenario));
}

export function groupChangeRecordsByMonth(
  records: ChangeRecord[],
): ChangeRecordMonthGroup[] {
  const grouped: Record<string, ChangeRecord[]> = {};
  records.forEach((item) => {
    const month = (item.created_at || '').slice(0, 7);
    if (!month) return;
    if (!grouped[month]) grouped[month] = [];
    grouped[month].push(item);
  });
  return Object.entries(grouped)
    .sort((left, right) => right[0].localeCompare(left[0]))
    .map(([month, list]) => ({
      month,
      list: [...list].sort(
        (left, right) =>
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      ),
      count: list.length,
    }));
}

export interface ChangeRecordRelationInfo {
  kind: 'add' | 'remove';
  src: string;
  dst: string;
  srcModel?: string;
  dstModel?: string;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }
  return value as Record<string, unknown>;
}

function readText(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '';
}

export function getChangeRecordRelationInfo(
  record: ChangeRecord | null | undefined,
): ChangeRecordRelationInfo | null {
  if (!record || record.label !== 'instance_association') return null;
  const data = asRecord(
    record.type === 'create_edge' ? record.after_data : record.before_data,
  );
  const edge = asRecord(data?.edge);
  if (!edge) return null;
  const src = asRecord(data?.src);
  const dst = asRecord(data?.dst);
  return {
    kind: record.type === 'create_edge' ? 'add' : 'remove',
    src: readText(src?.inst_name) || '--',
    dst: readText(dst?.inst_name) || '--',
    srcModel: readText(edge.src_model_id) || undefined,
    dstModel: readText(edge.dst_model_id) || undefined,
  };
}
