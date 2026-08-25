import * as echarts from 'echarts/core';

import type { ChartSnapshot } from './types';
import { CHART_SNAPSHOT_MAX_IMAGES, CHART_SNAPSHOT_TARGET_WIDTH } from './types';

export type { ChartSnapshot } from './types';
export { CHART_SNAPSHOT_MAX_IMAGES, CHART_SNAPSHOT_TARGET_WIDTH } from './types';

const asArray = <T>(value: T | T[] | undefined | null): T[] => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

const formatChartNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '';
  if (Number.isInteger(value) || Math.abs(value) >= 100) return String(Math.round(value));
  return value.toFixed(1);
};

const lastFinite = (values: unknown[]): string => {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    const value = values[i];
    if (typeof value === 'number' && Number.isFinite(value)) return formatChartNumber(value);
    if (typeof value === 'string' && value.trim()) return value;
    if (Array.isArray(value)) {
      const nested = lastFinite(value);
      if (nested) return nested;
    }
  }
  return '';
};

/** 监控趋势图 x 为 unix 秒；从 series 点里取横轴起止。 */
const formatAxisClock = (unixSec: number): string => {
  const date = new Date(unixSec * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
};

const isUnixSeconds = (value: number): boolean => value > 1_000_000_000 && value < 10_000_000_000;

export const timeSpanFromOption = (option: Record<string, unknown> | null | undefined): string => {
  if (!option) return '';
  let minTs = Number.POSITIVE_INFINITY;
  let maxTs = Number.NEGATIVE_INFINITY;
  const series = asArray(option.series as { data?: unknown[] } | { data?: unknown[] }[] | undefined);
  for (const item of series) {
    for (const point of asArray(item?.data)) {
      if (!Array.isArray(point) || typeof point[0] !== 'number' || !Number.isFinite(point[0])) continue;
      if (!isUnixSeconds(point[0])) continue;
      minTs = Math.min(minTs, point[0]);
      maxTs = Math.max(maxTs, point[0]);
    }
  }
  if (!Number.isFinite(minTs) || !Number.isFinite(maxTs) || maxTs < minTs) return '';
  const start = formatAxisClock(minTs);
  const end = formatAxisClock(maxTs);
  if (!start || !end) return '';
  return start === end ? start : `${start}~${end}`;
};

const pieSlices = (series: Array<{ name?: string; data?: unknown[] }>) => {
  const slices: Array<{ name: string; value: string }> = [];
  for (const item of series) {
    for (const point of asArray(item?.data)) {
      if (!point || typeof point !== 'object' || Array.isArray(point)) continue;
      const row = point as { name?: unknown; value?: unknown };
      const name = typeof row.name === 'string' ? row.name.trim() : '';
      const value =
        typeof row.value === 'number' && Number.isFinite(row.value)
          ? formatChartNumber(row.value)
          : typeof row.value === 'string' && row.value.trim()
            ? row.value.trim()
            : '';
      if (name || value) slices.push({ name, value });
    }
  }
  return slices;
};

export const captionFromOption = (option: Record<string, unknown> | null | undefined): string => {
  if (!option) return '图表';
  const titles = asArray(option.title as { text?: string } | { text?: string }[] | undefined)
    .map((item) => item?.text)
    .filter(Boolean);
  const series = asArray(option.series as { name?: string; data?: unknown[] } | { name?: string; data?: unknown[] }[] | undefined);
  const slices = pieSlices(series);
  const seriesNames = series.map((item) => item?.name).filter(Boolean) as string[];
  const names = seriesNames.length ? seriesNames : slices.map((item) => item.name).filter(Boolean);
  const yAxis = asArray(option.yAxis as { min?: unknown; max?: unknown } | { min?: unknown; max?: unknown }[] | undefined);
  const yRange = yAxis
    .map((axis) => {
      if (axis?.min == null && axis?.max == null) return '';
      return `${axis.min ?? '?'}~${axis.max ?? '?'}`;
    })
    .filter(Boolean);
  const latest = series.map((item) => lastFinite(asArray(item?.data))).filter(Boolean);
  const values = latest.length ? latest : slices.map((item) => item.value).filter(Boolean);
  const timeSpan = timeSpanFromOption(option);
  const parts = [
    titles[0] || '图表',
    names.length ? `序列: ${names.join(', ')}` : '',
    timeSpan ? `横轴: ${timeSpan}` : '',
    yRange.length ? `Y轴: ${yRange.join(', ')}` : '',
    values.length ? `最新值: ${values.join(', ')}` : '',
  ].filter(Boolean);
  return parts.join('；');
};

const resizeDataUrl = (dataUrl: string, maxWidth = CHART_SNAPSHOT_TARGET_WIDTH): Promise<string> =>
  new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const scale = Math.min(1, maxWidth / Math.max(image.width, 1));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(dataUrl);
        return;
      }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', 0.72));
    };
    image.onerror = () => resolve(dataUrl);
    image.src = dataUrl;
  });

const chartDomCandidates = (): HTMLElement[] => {
  const marked = Array.from(document.querySelectorAll<HTMLElement>('[_echarts_instance_]'));
  if (marked.length) return marked;
  return Array.from(document.querySelectorAll<HTMLElement>('div, canvas')).filter((node) => {
    try {
      return Boolean(echarts.getInstanceByDom(node));
    } catch {
      return false;
    }
  });
};

export const captureEchartsFromDoms = async (
  doms: HTMLElement[],
  limit = CHART_SNAPSHOT_MAX_IMAGES,
): Promise<ChartSnapshot[]> => {
  const images: ChartSnapshot[] = [];
  for (const dom of doms) {
    if (images.length >= limit) break;
    try {
      const instance = echarts.getInstanceByDom(dom);
      if (!instance) continue;
      const dataUrl = instance.getDataURL({ backgroundColor: '#fff', type: 'png', pixelRatio: 1 });
      if (!dataUrl) continue;
      const option = instance.getOption() as Record<string, unknown>;
      images.push({
        caption: captionFromOption(option),
        dataUrl: await resizeDataUrl(dataUrl),
      });
    } catch (error) {
      console.debug('[chart-snapshot] echarts capture failed', error);
    }
  }
  return images;
};

export const captureEchartsFromDom = async (limit = CHART_SNAPSHOT_MAX_IMAGES): Promise<ChartSnapshot[]> => {
  if (typeof document === 'undefined') return [];
  return captureEchartsFromDoms(chartDomCandidates(), limit);
};
