/**
 * 可观测图表统一色板。
 *
 * 数据序列使用冷色，红 / 橙 / 黄只表达告警级别，避免普通趋势被误读为告警。
 * Monitor 与 APM 的告警类图表都从这里取色，防止模块间视觉继续漂移。
 */
export const OBSERVABILITY_SERIES_COLORS = [
  '#5B8FF9',
  '#5AD8A6',
  '#F6BD16',
  '#EB6FB0',
  '#6DC8EC',
  '#945FB9',
  '#5D7092',
  '#1E9493',
] as const;

export const ALERT_LEVEL_COLORS = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
} as const;
