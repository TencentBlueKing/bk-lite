import type { BarItem } from '../../shared/widgets';
import { formatMetricValue } from '../../shared/utils/format';
import type { MetricUnit } from '../../shared/types';

export const FLEET_TOP_N = 5;

/** 与列表上报状态一致：normal/online 为正常，其余（失联）计为不健康。 */
export const isHostListUnhealthy = (status: unknown) => {
  const normalized = String(status || '').trim().toLowerCase();
  return normalized !== 'normal' && normalized !== 'online';
};

export const logicalInstanceId = (row: Record<string, unknown>) => {
  const values = row.instance_id_values;
  if (Array.isArray(values) && values[0] != null && String(values[0]).trim()) {
    return String(values[0]).trim();
  }
  const stored = String(row.instance_id || '');
  const matched = stored.match(/^\('([^']*)'/);
  return matched?.[1] || stored;
};

export const hostRowLabel = (row: Record<string, unknown>) =>
  String(row.instance_name || logicalInstanceId(row) || '--');

/** display_fields 回填 key 为 plugin::metric，单位转换后是 {value, unit}。 */
export const readDisplayMetric = (row: Record<string, unknown>, metricName: string): number | null => {
  const keys = Object.keys(row).filter(
    (key) => key === metricName || key.endsWith(`::${metricName}`)
  );
  for (const key of keys) {
    const cell = row[key];
    const raw = cell && typeof cell === 'object' && 'value' in (cell as object)
      ? (cell as { value?: unknown }).value
      : cell;
    const value = Number(raw);
    if (Number.isFinite(value)) return value;
  }
  return null;
};

const percentColor = (value: number) => {
  if (value >= 85) return 'var(--color-error)';
  if (value >= 70) return 'var(--color-warning)';
  return 'var(--color-primary)';
};

export const rankDisplayMetric = (
  rows: Array<Record<string, unknown>>,
  metricName: string,
  unit: MetricUnit
): BarItem[] => {
  const ranked = rows
    .map((row) => ({
      label: hostRowLabel(row),
      value: readDisplayMetric(row, metricName)
    }))
    .filter((item): item is { label: string; value: number } => item.value != null && Number.isFinite(item.value))
    .sort((left, right) => right.value - left.value)
    .slice(0, FLEET_TOP_N);
  const peak = ranked.length ? Math.max(...ranked.map((item) => item.value)) : 0;
  const max = peak > 0 ? peak : 1;
  return ranked.map((item) => {
    const formatted = formatMetricValue(item.value, unit);
    return {
      label: item.label,
      value: item.value,
      display: `${formatted.value}${formatted.unit || ''}`,
      color: unit === 'percent' ? percentColor(item.value) : 'var(--color-error)',
      max
    };
  });
};

export const averageDisplayMetric = (
  rows: Array<Record<string, unknown>>,
  metricName: string
): number | null => {
  const values = rows
    .map((row) => readDisplayMetric(row, metricName))
    .filter((value): value is number => value != null);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
};

export interface FleetHintGroup {
  label: string;
  values: string[];
}

/** 只展示实例上已经有的云区域 / 摘要字段，不构造任意标签分面。 */
export const fleetHintGroups = (rows: Array<Record<string, unknown>>): FleetHintGroup[] => {
  const regions = new Set<string>();
  const facts = new Map<string, Set<string>>();
  rows.forEach((row) => {
    if (row.cloud_region_id != null && String(row.cloud_region_id).trim()) {
      regions.add(String(row.cloud_region_id));
    }
    const summary = row.summary_facts;
    if (!summary || typeof summary !== 'object') return;
    Object.entries(summary as Record<string, unknown>).forEach(([key, value]) => {
      if (!/os|region|instance_type|cloud/i.test(key)) return;
      if (value == null || typeof value === 'object') return;
      const text = String(value).trim();
      if (!text) return;
      const bucket = facts.get(key) || new Set<string>();
      bucket.add(text);
      facts.set(key, bucket);
    });
  });
  const groups: FleetHintGroup[] = [];
  if (regions.size) {
    groups.push({ label: '云区域', values: Array.from(regions).slice(0, 8) });
  }
  facts.forEach((values, key) => {
    groups.push({ label: key, values: Array.from(values).slice(0, 8) });
  });
  return groups;
};
