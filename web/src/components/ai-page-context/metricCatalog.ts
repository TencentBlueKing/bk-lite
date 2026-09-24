import type { MetricSparkline } from '@/components/chart-snapshot/sparkline';
import { sparklineFromChartRows } from '@/components/chart-snapshot/sparkline';
import type { AiContextSection } from '@/components/ai-page-context/types';

export interface MetricCatalogChild {
  id?: number;
  name?: string;
  display_name?: string;
  unit?: string;
  viewData?: Array<Record<string, unknown>>;
}

export interface MetricCatalogGroup {
  name?: string;
  display_name?: string;
  child?: MetricCatalogChild[];
}

export const buildMetricCatalogLines = (groups: MetricCatalogGroup[]): {
  catalog: string;
  series: MetricSparkline[];
  loaded: number;
  total: number;
} => {
  const catalogLines: string[] = [];
  const series: MetricSparkline[] = [];
  let total = 0;
  let loaded = 0;
  for (const group of groups) {
    const children = Array.isArray(group.child) ? group.child : [];
    if (!children.length) continue;
    const groupName = group.display_name || group.name || '未分组';
    const childBits: string[] = [];
    for (const child of children) {
      total += 1;
      const name = child.display_name || child.name || '--';
      const metric = child.name || '';
      const hasSeries = Array.isArray(child.viewData) && child.viewData.length > 0;
      if (hasSeries) {
        loaded += 1;
        const spark = sparklineFromChartRows(child.viewData as Array<Record<string, unknown>>, {
          name,
          group: groupName,
          metric,
          unit: child.unit,
        });
        if (spark) series.push(spark);
        childBits.push(metric ? `${name} (${metric})` : name);
      } else {
        childBits.push(metric ? `${name} (${metric}, 未加载)` : `${name} (未加载)`);
      }
    }
    catalogLines.push(`${groupName}: ${childBits.join('；')}`);
  }
  return {
    catalog: catalogLines.join('\n'),
    series,
    loaded,
    total,
  };
};

export const metricCatalogSections = (
  built: ReturnType<typeof buildMetricCatalogLines>,
  extraIdentity: string[] = [],
): AiContextSection[] => {
  const remaining = Math.max(0, built.total - built.loaded);
  const identity = [
    ...extraIdentity,
    built.total ? `目录 ${built.total} 项，已加载曲线 ${built.loaded}` : '',
    remaining ? `还有 ${remaining} 个未加载` : '',
  ].filter(Boolean);
  return [
    ...(identity.length
      ? [{
        id: 'metric-identity',
        label: '全量指标',
        content: identity.join('\n'),
        priority: 10,
      }]
      : []),
    ...(built.catalog
      ? [{
        id: 'metric-catalog',
        label: '指标目录',
        content: built.catalog,
        priority: 8,
      }]
      : []),
    ...(built.series.length
      ? [{
        id: 'metric-series',
        label: '已加载曲线',
        content: JSON.stringify(built.series),
        priority: 7,
      }]
      : []),
  ];
};
