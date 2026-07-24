import type { SimpleDashboardConfig, SimpleMetricConfig } from './simple-dashboard-core';

export interface TargetDashboardSpec { routeKey: string; title: string; objectName: string; instanceType: string; collectType: string; collectionStatusQuery?: string; meta: string[]; metrics: SimpleMetricConfig[]; summary: Array<{ title: string; metric: string; icon: 'health' | 'database' | 'node' | 'clock' | 'memory' | 'backlog' | 'publish' | 'thunder'; detail: string; down?: boolean }>; charts: Array<{ title: string; subtitle: string; metrics: string[]; detail: string }>; detailTitle: string; }
const color = ['#2f6bff', '#ff8a1f', '#ff4d4f', '#8a5cff', '#13c2c2'];
export const createTargetDashboardConfig = (spec: TargetDashboardSpec): SimpleDashboardConfig => ({
  routeKey: spec.routeKey, pageTitle: `${spec.title}监控仪表盘`, objectFallbackName: spec.objectName, instanceType: spec.instanceType,
  collectionStatusQuery: spec.collectionStatusQuery ?? `count({instance_type='${spec.instanceType}', collect_type='${spec.collectType}', __$labels__}) by (instance_id)`, metaItems: spec.meta, metrics: spec.metrics,
  summaryCards: spec.summary.map((item, index) => ({ title: item.title, metric: item.metric, color: color[index], icon: item.icon, compare: item.down, compareFavorableDirection: item.down ? 'down' : undefined, guide: [{ label: item.title, detail: item.detail }] })),
  charts: spec.charts.map((chart) => ({ title: chart.title, subtitle: chart.subtitle, metric: chart.metrics[0], guide: [{ label: chart.title, detail: chart.detail }], series: chart.metrics.map((metric, index) => ({ metric, label: spec.metrics.find((item) => item.name === metric)?.display_name ?? metric, color: color[index], unit: spec.metrics.find((item) => item.name === metric)?.unit })) })),
  details: [{ title: spec.detailTitle, subtitle: '用于发现异常后的定向排查。', rows: spec.summary.map((item) => ({ label: item.title, metric: item.metric, unit: spec.metrics.find((metric) => metric.name === item.metric)?.unit, tone: item.down ? 'warning' : 'normal' })) }],
});
