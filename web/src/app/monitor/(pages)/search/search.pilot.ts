import type {
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { PAGE_CONTEXT_MAX_IMAGES } from '@/components/ai-page-context/types';
import { sparklineFromChartRows } from '@/components/chart-snapshot/sparkline';
import type { ChartItem, SearchPayload } from '@/app/monitor/types/search';
import { cleanLabel } from '@/components/ai-page-context/domSnapshot';
import { listSelectedMetricIds } from './searchQueryLogic';

export interface PublishedSearchSnapshot {
  payload: SearchPayload | null;
  charts: ChartItem[];
  timeLabel?: string;
}

let published: PublishedSearchSnapshot | null = null;

export const publishSearchSnapshot = (next: PublishedSearchSnapshot | null) => {
  published = next;
};

export const getPublishedSearchSnapshot = () => published;

const objectName = (payload: SearchPayload, group = payload.activeGroup) =>
  payload.objectsMap[String(group.object)]?.display_name
  || payload.objectsMap[String(group.object)]?.name
  || '';

const pluginName = (payload: SearchPayload, group = payload.activeGroup) => {
  const plugins = payload.pluginsMap[String(group.object)] || [];
  const plugin = plugins.find((item) => String(item.id) === String(group.plugin));
  return plugin?.display_name || plugin?.name || '';
};

const instanceNames = (payload: SearchPayload, group = payload.activeGroup) => {
  const instances = payload.instancesMap[String(group.object)] || [];
  return group.instanceIds
    .map((id) => instances.find((item) => item.instance_id === id)?.instance_name || id)
    .filter(Boolean);
};

const metricName = (payload: SearchPayload, group = payload.activeGroup) => {
  const metrics = payload.metricsMap[String(group.plugin || group.object)] || [];
  const names = listSelectedMetricIds(group.metric)
    .map((id) => metrics.find((item) => String(item.id) === String(id)))
    .map((metric) => metric?.display_name || metric?.name || '')
    .filter(Boolean);
  if (names.length) return names.join('、');
  return group.legacyMetricName || '';
};

export const summarizeSearchForm = (payload: SearchPayload | null, timeLabel = ''): string[] => {
  if (!payload?.activeGroup) {
    return ['尚未点搜索', timeLabel ? `时间窗: ${timeLabel}` : ''].filter(Boolean);
  }
  const group = payload.activeGroup;
  const filters = (group.conditions || [])
    .filter((item) => item.label && item.value)
    .map((item) => `${item.label}${item.condition || '='}${item.value}`);
  return [
    '正在查看指标搜索',
    objectName(payload) ? `对象: ${objectName(payload)}` : '',
    pluginName(payload) ? `插件: ${pluginName(payload)}` : '',
    instanceNames(payload).length ? `实例: ${instanceNames(payload).join('、')}` : '',
    metricName(payload) ? `指标: ${metricName(payload)}` : '',
    group.aggregation ? `聚合: ${group.aggregation}` : '',
    filters.length ? `维度过滤: ${filters.join('；')}` : '',
    timeLabel ? `时间窗: ${timeLabel}` : '',
  ].filter(Boolean);
};

const timeLabelFromDom = (): string =>
  cleanLabel(document.querySelector('.ant-select-selection-item')?.textContent || '');

export function getMessage(): PageContextMessage {
  const snap = getPublishedSearchSnapshot();
  const chartCount = snap?.charts.length || 0;
  return {
    title: 'monitor-search',
    currentTime: [timeLabelFromDom(), String(chartCount), snap?.timeLabel || ''].filter(Boolean).join('::'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const snap = getPublishedSearchSnapshot();
  const timeLabel = snap?.timeLabel || timeLabelFromDom();
  const form = summarizeSearchForm(snap?.payload || null, timeLabel);
  const charts = snap?.charts || [];
  const series = charts.length > PAGE_CONTEXT_MAX_IMAGES
    ? charts
      .map((item) => sparklineFromChartRows(item.data as Array<Record<string, unknown>>, {
        name: item.metric?.display_name || item.metric?.name || item.groupName,
        group: item.groupName,
        metric: item.metric?.name,
        unit: item.unit,
      }))
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
    : [];
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: typeof document === 'undefined' ? '指标搜索' : document.title || '指标搜索',
    sections: [
      {
        id: 'search-form',
        label: '查询条件',
        content: form.join('\n'),
        priority: 10,
      },
      ...(series.length
        ? [{
          id: 'metric-series',
          label: '已加载曲线',
          content: JSON.stringify(series),
          priority: 7,
        }]
        : []),
    ],
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  const base = getTextContext();
  const snap = getPublishedSearchSnapshot();
  const charts = snap?.charts || [];
  if (!charts.length || charts.length > PAGE_CONTEXT_MAX_IMAGES) {
    return base;
  }
  const roots = Array.from(document.querySelectorAll<HTMLElement>('.recharts-wrapper'));
  const images = await toolkit.captureRechartsFromDoms(roots, PAGE_CONTEXT_MAX_IMAGES);
  return {
    ...base,
    images,
    sections: [
      ...(base.sections || []),
      ...(images.length
        ? [{
          id: 'visible-charts',
          label: '可见图表',
          content: images.map((image, index) => `${index + 1}. ${image.caption || '图表'}`).join('\n'),
          priority: 9,
        }]
        : []),
    ],
  };
}
