import * as echarts from 'echarts/core';

import type { AiContextImage } from './types';
import { PAGE_CONTEXT_MAX_IMAGES } from './types';

const TARGET_WIDTH = 600;

const asArray = <T>(value: T | T[] | undefined | null): T[] => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

const lastFinite = (values: unknown[]): string => {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    const value = values[i];
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
    if (typeof value === 'string' && value.trim()) return value;
    if (Array.isArray(value)) {
      const nested = lastFinite(value);
      if (nested) return nested;
    }
  }
  return '';
};

export const captionFromOption = (option: Record<string, unknown> | null | undefined): string => {
  if (!option) return '图表';
  const titles = asArray(option.title as { text?: string } | { text?: string }[] | undefined)
    .map((item) => item?.text)
    .filter(Boolean);
  const series = asArray(option.series as { name?: string; data?: unknown[] } | { name?: string; data?: unknown[] }[] | undefined);
  const names = series.map((item) => item?.name).filter(Boolean) as string[];
  const yAxis = asArray(option.yAxis as { min?: unknown; max?: unknown } | { min?: unknown; max?: unknown }[] | undefined);
  const yRange = yAxis
    .map((axis) => {
      if (axis?.min == null && axis?.max == null) return '';
      return `${axis.min ?? '?'}~${axis.max ?? '?'}`;
    })
    .filter(Boolean);
  const latest = series.map((item) => lastFinite(asArray(item?.data))).filter(Boolean);
  const parts = [
    titles[0] || '图表',
    names.length ? `序列: ${names.join(', ')}` : '',
    yRange.length ? `Y轴: ${yRange.join(', ')}` : '',
    latest.length ? `最新值: ${latest.join(', ')}` : '',
  ].filter(Boolean);
  return parts.join('；');
};

const resizeDataUrl = (dataUrl: string, maxWidth = TARGET_WIDTH): Promise<string> =>
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

export const captureEchartsFromDom = async (limit = PAGE_CONTEXT_MAX_IMAGES): Promise<AiContextImage[]> => {
  if (typeof document === 'undefined') return [];
  const images: AiContextImage[] = [];
  for (const dom of chartDomCandidates()) {
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
      console.warn('[ai-page-context] echarts capture failed', error);
    }
  }
  return images;
};
