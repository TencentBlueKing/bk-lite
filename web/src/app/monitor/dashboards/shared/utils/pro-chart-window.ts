import type { ChartData, TimeValuesProps } from '@/app/monitor/types';
import { resolveCollectionStatusRange } from './collection-status';

/** 专业盘折线 X 轴与事件条共用的绝对窗口，单位秒。 */
export interface ProChartWindow {
  startSec: number;
  endSec: number;
}

export const proChartWindowFromMs = (startMs: number, endMs: number): ProChartWindow | null => {
  const start = Number(startMs);
  const end = Number(endMs);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  return { startSec: start / 1000, endSec: end / 1000 };
};

export const proChartWindowFromTimeValues = (timeValues: TimeValuesProps): ProChartWindow | null => {
  const range = resolveCollectionStatusRange(timeValues);
  if (!range) return null;
  return proChartWindowFromMs(range.startMs, range.endMs);
};

/**
 * 顶栏刚切换、查询还停在上一档时，先用新档，避免轴仍画出旧窗。
 * 同一档（含刷新后重新冻结的 now）用已发起查询的窗口，让轴和 from–to 对齐。
 */
export const selectProChartWindow = (
  timeValues: TimeValuesProps,
  queryTimeRange?: { startMs: number; endMs: number } | null
): ProChartWindow | null => {
  const selected = proChartWindowFromTimeValues(timeValues);
  const queried = queryTimeRange
    ? proChartWindowFromMs(queryTimeRange.startMs, queryTimeRange.endMs)
    : null;
  if (!queried) return selected;
  if (!selected) return queried;
  const selectedSpan = selected.endSec - selected.startSec;
  const queriedSpan = queried.endSec - queried.startSec;
  if (Math.abs(selectedSpan - queriedSpan) > 1) return selected;
  return queried;
};

/**
 * 顶栏档位和已发起查询的跨度还没对齐。相对预设的 now 会滑动，只比跨度，
 * 避免刷新后一两秒就被当成新窗口。
 */
export const isProChartWindowPending = (
  timeValues: TimeValuesProps,
  queryTimeRange?: { startMs: number; endMs: number } | null
): boolean => {
  const selected = proChartWindowFromTimeValues(timeValues);
  const queried = queryTimeRange
    ? proChartWindowFromMs(queryTimeRange.startMs, queryTimeRange.endMs)
    : null;
  if (!selected || !queried) return false;
  const selectedSpan = selected.endSec - selected.startSec;
  const queriedSpan = queried.endSec - queried.startSec;
  return Math.abs(selectedSpan - queriedSpan) > 1;
};

/** 丢掉窗口外的点。空结果表示该窗没有可画的序列，不能改去画别的默认窗。 */
export const clipChartDataToWindow = (
  data: ChartData[],
  chartWindow: ProChartWindow | null
): ChartData[] => {
  if (!chartWindow || !data.length) return data;
  return data.filter((point) => {
    const time = Number(point.time);
    return Number.isFinite(time) && time >= chartWindow.startSec && time <= chartWindow.endSec;
  });
};

/** 事件条上的时间点。无法解析的时间不算在窗口内。 */
export const alertEventInsideWindow = (at: string, chartWindow: ProChartWindow | null): boolean => {
  if (!chartWindow) return true;
  const time = Date.parse(at);
  if (!Number.isFinite(time)) return false;
  return time >= chartWindow.startSec * 1000 && time <= chartWindow.endSec * 1000;
};
