import {
  listInteractionTemplateBodies,
  readChartLinkPoint,
  type ChartLinkPoint,
} from '@/app/ops-analysis/utils/interactionLink';

const DATA_FIELD_PREFIX = '__data.fields.';

const SERIES_VALUE_BODIES = new Set([
  '__series.name',
  '__value.numeric',
  '__value.text',
  '__value.raw',
]);

export const chartLinkPointHasNumeric = (point: ChartLinkPoint | undefined) =>
  typeof point?.numeric === 'number' && Number.isFinite(point.numeric);

/** 模板只用横轴、时间或画布筛选时，空列也能跳。用了数值或系列名则必须有值。 */
export const trendTemplateNeedsPointValue = (
  template: string | undefined,
  axisFields: Array<string | undefined> = [],
) => {
  const axis = new Set(
    axisFields
      .map((field) => field?.trim())
      .filter((field): field is string => Boolean(field)),
  );
  return listInteractionTemplateBodies(template || '').some((body) => {
    if (body === '__value.time') return false;
    if (SERIES_VALUE_BODIES.has(body) || body.startsWith('__value.') || body.startsWith('__series.')) {
      return true;
    }
    if (body.startsWith(DATA_FIELD_PREFIX)) {
      return !axis.has(body.slice(DATA_FIELD_PREFIX.length));
    }
    return false;
  });
};

export interface TrendColumnCandidate {
  point?: ChartLinkPoint;
  pixelY?: number | null;
}

export const resolveTrendColumnPoint = ({
  template,
  axisFields = [],
  candidates,
  pointerY,
}: {
  template?: string;
  axisFields?: Array<string | undefined>;
  candidates: TrendColumnCandidate[];
  pointerY?: number;
}): ChartLinkPoint | undefined => {
  const present = candidates.filter((item): item is TrendColumnCandidate & { point: ChartLinkPoint } =>
    Boolean(item.point));
  if (!present.length) return undefined;
  const fields = [
    ...axisFields,
    ...present.map((item) => item.point.axisField),
  ];
  if (!trendTemplateNeedsPointValue(template, fields)) {
    return present[0].point;
  }
  const valued = present.filter((item) => chartLinkPointHasNumeric(item.point));
  if (!valued.length) return undefined;
  if (valued.length === 1 || pointerY == null) return valued[0].point;
  let best = valued[0];
  let bestDistance = Number.POSITIVE_INFINITY;
  valued.forEach((item) => {
    if (typeof item.pixelY !== 'number' || !Number.isFinite(item.pixelY)) return;
    const distance = Math.abs(item.pixelY - pointerY);
    if (distance < bestDistance) {
      best = item;
      bestDistance = distance;
    }
  });
  return Number.isFinite(bestDistance) ? best.point : valued[0].point;
};

export const trendColumnCanOpen = (
  template: string | undefined,
  axisFields: Array<string | undefined>,
  points: Array<ChartLinkPoint | undefined>,
) => Boolean(resolveTrendColumnPoint({
  template,
  axisFields,
  candidates: points.map((point) => ({ point })),
}));

export const trendPointsFromTooltip = (params: unknown): ChartLinkPoint[] => {
  const list = Array.isArray(params) ? params : params ? [params] : [];
  return list.flatMap((item) => {
    const point = readChartLinkPoint((item as { data?: unknown } | undefined)?.data);
    return point ? [point] : [];
  });
};

export const categoryIndexFromAxisValue = (
  value: unknown,
  categoryCount: number,
): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const index = Math.round(value);
    if (index < 0 || index >= categoryCount) return undefined;
    return index || 0;
  }
  return undefined;
};

export interface TrendGridChart {
  containPixel: (finder: { gridIndex: number }, value: number[]) => boolean;
  convertFromPixel: (finder: { gridIndex: number }, value: number[]) => unknown;
  convertToPixel: (finder: { seriesIndex: number }, value: unknown[]) => unknown;
  getZr: () => {
    on: (event: string, handler: (event: { offsetX: number; offsetY: number }) => void) => void;
    off: (event: string, handler: (event: { offsetX: number; offsetY: number }) => void) => void;
  };
}

export const readTrendCategoryIndex = (
  chart: TrendGridChart,
  offsetX: number,
  offsetY: number,
  categoryCount: number,
) => {
  const pixel = [offsetX, offsetY];
  if (!chart.containPixel({ gridIndex: 0 }, pixel)) return undefined;
  const converted = chart.convertFromPixel({ gridIndex: 0 }, pixel);
  const axisValue = Array.isArray(converted) ? converted[0] : undefined;
  return categoryIndexFromAxisValue(axisValue, categoryCount);
};

export const trendSeriesPixelY = (
  chart: TrendGridChart,
  seriesIndex: number,
  categoryIndex: number,
  numeric: number,
) => {
  try {
    const pixel = chart.convertToPixel({ seriesIndex }, [categoryIndex, numeric]);
    return Array.isArray(pixel) && typeof pixel[1] === 'number' ? pixel[1] : null;
  } catch {
    return null;
  }
};

export interface TrendColumnSeries {
  name?: string;
  points?: Array<ChartLinkPoint | undefined>;
}

/** 绘图区点击与 tooltip footer 共用：先换算类目，再按模板决定能不能跳。 */
export const resolveTrendGridClick = ({
  chart,
  offsetX,
  offsetY,
  categoryCount,
  template,
  axisFields,
  series,
  legendSelected,
}: {
  chart: TrendGridChart;
  offsetX: number;
  offsetY: number;
  categoryCount: number;
  template?: string;
  axisFields?: Array<string | undefined>;
  series: TrendColumnSeries[];
  legendSelected?: Record<string, boolean>;
}): ChartLinkPoint | undefined => {
  const categoryIndex = readTrendCategoryIndex(chart, offsetX, offsetY, categoryCount);
  if (categoryIndex == null) return undefined;
  const candidates = series.flatMap((item, seriesIndex) => {
    if (item.name != null && legendSelected?.[item.name] === false) return [];
    const point = item.points?.[categoryIndex];
    const numeric = point?.numeric;
    const pixelY = typeof numeric === 'number' && Number.isFinite(numeric)
      ? trendSeriesPixelY(chart, seriesIndex, categoryIndex, numeric)
      : null;
    return [{ point, pixelY }];
  });
  return resolveTrendColumnPoint({
    template,
    axisFields,
    candidates,
    pointerY: offsetY,
  });
};

export const bindTrendGridClick = (
  chart: TrendGridChart,
  onClick: (offsetX: number, offsetY: number) => void,
) => {
  const zr = chart.getZr();
  const handle = (event: { offsetX: number; offsetY: number }) => {
    if (typeof event.offsetX !== 'number' || typeof event.offsetY !== 'number') return;
    onClick(event.offsetX, event.offsetY);
  };
  zr.on('click', handle);
  return () => {
    try {
      zr.off('click', handle);
    } catch {
      // 图表实例已销毁时解绑会失败，监听也已随实例释放。
    }
  };
};
