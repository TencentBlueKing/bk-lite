export type DisplayFieldType = 'enum' | 'progress' | 'value';

interface MetricMeta {
  data_type?: string;
  unit?: string;
}

const PERCENT_UNITS = new Set(['percent', '%']);

/**
 * 由指标元数据推导视图列表展示类型。
 * 规则：Enum -> enum；百分比单位 -> progress；其余 -> value。
 */
export function getDisplayFieldType(metric?: MetricMeta): DisplayFieldType {
  if (!metric) return 'value';
  if (metric.data_type === 'Enum') return 'enum';
  if (metric.unit && PERCENT_UNITS.has(metric.unit)) return 'progress';
  return 'value';
}
