import type { ChartSnapshot } from './types';
import { CHART_SNAPSHOT_MAX_IMAGES, CHART_SNAPSHOT_TARGET_WIDTH } from './types';

const resizeDataUrl = (dataUrl: string, maxWidth = CHART_SNAPSHOT_TARGET_WIDTH): Promise<string> =>
  new Promise((resolve) => {
    if (typeof Image === 'undefined') {
      resolve(dataUrl);
      return;
    }
    let settled = false;
    const finish = (next: string) => {
      if (settled) return;
      settled = true;
      resolve(next);
    };
    // jsdom 的 Image 对 svg data URL 既不 onload 也不 onerror，不能一直等。
    const timer = setTimeout(() => finish(dataUrl), 50);
    const image = new Image();
    image.onload = () => {
      clearTimeout(timer);
      const scale = Math.min(1, maxWidth / Math.max(image.width, 1));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        finish(dataUrl);
        return;
      }
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      try {
        finish(canvas.toDataURL('image/jpeg', 0.72));
      } catch {
        finish(dataUrl);
      }
    };
    image.onerror = () => {
      clearTimeout(timer);
      finish(dataUrl);
    };
    image.src = dataUrl;
  });

export const rechartsSvgFromRoot = (root: HTMLElement): SVGSVGElement | null => {
  if (root instanceof SVGSVGElement) return root;
  return root.querySelector('svg');
};

export const svgElementToDataUrl = (svg: SVGSVGElement): string => {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  if (!clone.getAttribute('xmlns')) {
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  }
  const xml = new XMLSerializer().serializeToString(clone);
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
};

export const captionFromRechartsRoot = (root: HTMLElement): string => {
  const collapseTitle = root.closest('.collapse-content')
    ?.previousElementSibling
    ?.querySelector('.title');
  const cardTitle = root.closest('.ant-card')?.querySelector('.ant-card-head-title');
  const heading = collapseTitle || cardTitle
    || root.closest('section, [class*="chartWrapper"], [class*="chart"]')?.querySelector('h1, h2, h3, h4, .title');
  const text = (heading?.textContent || root.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  return text || '图表';
};

export const captureRechartsFromDoms = async (
  roots: HTMLElement[],
  limit = CHART_SNAPSHOT_MAX_IMAGES,
): Promise<ChartSnapshot[]> => {
  const images: ChartSnapshot[] = [];
  for (const root of roots) {
    if (images.length >= limit) break;
    try {
      const svg = rechartsSvgFromRoot(root);
      if (!svg) continue;
      const dataUrl = svgElementToDataUrl(svg);
      if (!dataUrl) continue;
      images.push({
        caption: captionFromRechartsRoot(root),
        dataUrl: await resizeDataUrl(dataUrl),
      });
    } catch (error) {
      console.debug('[chart-snapshot] recharts capture failed', error);
    }
  }
  return images;
};
