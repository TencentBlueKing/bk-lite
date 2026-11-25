import type { LineBarChartData } from '@/app/ops-analysis/utils/chartDataTransform';
import { referenceLineColor, type ChartDisplay } from '@/app/ops-analysis/utils/chartDisplay';

/** Stable id of the silent series that carries reference and threshold marks. */
export const REFERENCE_GUIDE_SERIES_ID = 'ops-reference-guide';

export function withoutReferenceGuideSeries<T extends { id?: string }>(
  series: readonly T[],
): T[] {
  return series.filter((item) => item.id !== REFERENCE_GUIDE_SERIES_ID);
}

/**
 * Structural slice of the option comBar / comLine already build.
 * yAxis is the left axis object. dataZoom is not on this type,
 * so the painter cannot replace brush zoom.
 * The painter is the only writer of series.stack, the guide series, and yAxis.min / yAxis.max.
 */
export interface BarLineGuideSeries {
  id?: string;
  name?: string;
  type?: string;
  data?: unknown[];
  stack?: string;
  yAxisIndex?: number;
  silent?: boolean;
  legendHoverLink?: boolean;
  symbol?: string;
  tooltip?: { show?: boolean };
  lineStyle?: { opacity?: number; width?: number; color?: string };
  itemStyle?: { opacity?: number; color?: string };
  emphasis?: { disabled?: boolean };
  markLine?: unknown;
}

export interface BarLineGuideOption {
  series: BarLineGuideSeries[];
  yAxis: {
    min?: number;
    max?: number;
  };
}

export interface BarLineGuideInput {
  readonly chart: 'bar' | 'line';
  readonly display: ChartDisplay;
  readonly data: LineBarChartData;
  readonly thresholdColors?: readonly { readonly value?: unknown; readonly color?: string }[] | undefined;
  readonly scale: (designPx: number) => number;
  readonly scaleFloat: (designPx: number) => number;
}

interface GuideMark {
  yAxis: number;
  lineStyle: {
    color: string;
    type: 'dashed';
    width: number;
  };
  label: {
    show: true;
    position: 'insideEndTop' | 'insideEndBottom';
    distance: number;
    formatter: string;
    color: string;
    fontSize: number;
  };
}

const finiteCell = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const plottedExtent = (
  data: LineBarChartData,
  stacked: boolean,
): { min: number; max: number } | undefined => {
  if (!stacked) {
    let seen = false;
    let extentMin = 0;
    let extentMax = 0;
    const add = (value: number | null | undefined) => {
      if (!finiteCell(value)) return;
      if (!seen) {
        seen = true;
        extentMin = value;
        extentMax = value;
        return;
      }
      if (value < extentMin) extentMin = value;
      if (value > extentMax) extentMax = value;
    };
    data.values?.forEach(add);
    data.series?.forEach((series) => series.data.forEach(add));
    if (!seen) return undefined;
    return { min: extentMin, max: extentMax };
  }

  let length = Math.max(data.categories.length, data.values?.length ?? 0);
  (data.series ?? []).forEach((series) => {
    if (series.data.length > length) length = series.data.length;
  });
  let seen = false;
  let anyNegative = false;
  let extentMax = 0;
  let extentMin = 0;
  for (let index = 0; index < length; index += 1) {
    let positive = 0;
    let negative = 0;
    const add = (value: number | null | undefined) => {
      if (!finiteCell(value)) return;
      seen = true;
      if (value > 0) positive += value;
      else if (value < 0) negative += value;
    };
    add(data.values?.[index]);
    data.series?.forEach((series) => add(series.data[index]));
    if (positive > extentMax) extentMax = positive;
    if (negative < extentMin) extentMin = negative;
    if (negative < 0) anyNegative = true;
  }
  if (!seen) return undefined;
  return {
    min: anyNegative ? extentMin : 0,
    max: extentMax,
  };
};

const guideMark = (
  value: number,
  color: string,
  formatter: string,
  position: GuideMark['label']['position'],
  input: BarLineGuideInput,
): GuideMark => ({
  yAxis: value,
  lineStyle: {
    color,
    type: 'dashed',
    width: input.scaleFloat(1.5),
  },
  label: {
    show: true,
    position,
    distance: input.scale(4),
    formatter,
    color,
    fontSize: input.scale(10),
  },
});

/**
 * A line above the data becomes the axis max, so it sits on the top edge.
 * The name goes under the stroke, inside the plot. Padding the axis past the
 * value draws a second split line above the guide.
 */
const referenceLabelPosition = (
  value: number,
  extent: { min: number; max: number } | undefined,
  lines: readonly { readonly value: number }[],
): GuideMark['label']['position'] => {
  if (extent) return value > extent.max ? 'insideEndBottom' : 'insideEndTop';
  const highest = Math.max(...lines.map((line) => line.value));
  return value >= highest ? 'insideEndBottom' : 'insideEndTop';
};

const thresholdMarks = (input: BarLineGuideInput): GuideMark[] => {
  const marks: GuideMark[] = [];
  (input.thresholdColors ?? []).forEach((threshold) => {
    const value = Number(threshold.value);
    if (!Number.isFinite(value) || value === 0) return;
    marks.push(guideMark(value, threshold.color ?? '', String(value), 'insideEndTop', input));
  });
  return marks;
};

const clearAxisEnds = (option: BarLineGuideOption): void => {
  if (!option.yAxis) return;
  delete option.yAxis.min;
  delete option.yAxis.max;
};

const applyValueAxis = (
  option: BarLineGuideOption,
  lines: readonly { readonly value: number }[],
  extent: { min: number; max: number } | undefined,
): void => {
  if (!option.yAxis || lines.length === 0) {
    clearAxisEnds(option);
    return;
  }
  const inside = extent !== undefined && lines.every(
    (line) => line.value >= extent.min && line.value <= extent.max,
  );
  if (inside) {
    clearAxisEnds(option);
    return;
  }
  if (!extent) {
    const values = lines.map((line) => line.value);
    option.yAxis.min = Math.min(...values);
    option.yAxis.max = Math.max(...values);
    return;
  }
  const below = lines.filter((line) => line.value < extent.min).map((line) => line.value);
  const above = lines.filter((line) => line.value > extent.max).map((line) => line.value);
  if (below.length > 0) option.yAxis.min = Math.min(...below);
  else delete option.yAxis.min;
  if (above.length > 0) option.yAxis.max = Math.max(...above);
  else delete option.yAxis.max;
};

const dropGuideSeries = (series: BarLineGuideSeries[]): void => {
  for (let index = series.length - 1; index >= 0; index -= 1) {
    if (series[index]?.id === REFERENCE_GUIDE_SERIES_ID) series.splice(index, 1);
  }
};

/**
 * Mutates `option` in place. A second call with the same input leaves the same stack,
 * the same guide series, and the same min/max.
 * With no stack, no reference lines, and no drawable thresholds, data points are not scanned.
 * Marks live on a silent series bound to the left axis, so legend toggles and a right
 * axis on the first series do not move or hide them.
 */
export function applyBarLineGuides(option: BarLineGuideOption, input: BarLineGuideInput): void {
  dropGuideSeries(option.series);
  const stack = input.chart === 'bar' && input.display.stackBars === true;
  option.series.forEach((series) => {
    if (stack) series.stack = 'total';
    else delete series.stack;
    delete series.markLine;
  });

  const lines = input.display.referenceLines ?? [];
  const thresholds = thresholdMarks(input);
  if (!stack && lines.length === 0 && thresholds.length === 0) {
    clearAxisEnds(option);
    return;
  }

  const extent = lines.length > 0
    ? plottedExtent(input.data, input.chart === 'bar' && input.display.stackBars === true)
    : undefined;
  if (option.series.length > 0 && (lines.length > 0 || thresholds.length > 0)) {
    option.series.push({
      id: REFERENCE_GUIDE_SERIES_ID,
      name: '',
      type: 'line',
      data: [],
      yAxisIndex: 0,
      silent: true,
      legendHoverLink: false,
      symbol: 'none',
      tooltip: { show: false },
      lineStyle: { opacity: 0, width: 0 },
      itemStyle: { opacity: 0 },
      emphasis: { disabled: true },
      markLine: {
        silent: true,
        symbol: 'none',
        data: [
          ...thresholds,
          ...lines.map((line) => guideMark(
            line.value,
            line.color ?? referenceLineColor(),
            line.name,
            referenceLabelPosition(line.value, extent, lines),
            input,
          )),
        ],
      },
    });
  }

  applyValueAxis(option, lines, extent);
}
