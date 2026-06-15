import { TimeValuesProps } from '@/app/monitor/types';
import { getRecentTimeRange } from '@/app/monitor/utils/common';

/**
 * 把"近 N 分钟"这类相对时间窗(originValue 模式,每次取数都现算 dayjs() now)
 * 解析并冻结成一个绝对的 [start, end] 窗口。
 *
 * 同一个面板的多条序列是各自独立发起 range 查询的,如果每条都各自现算时间窗,
 * start 锚点会相差几十~几百毫秒,Prometheus/VM 按 start+k*step 返回时间戳,
 * 网格随之错位、交错,合并(按精确时间戳做 key)后每行只有一条序列有值、
 * 另一条被填 null;connectNulls 把线连满,但 axis tooltip 在同一个 x 上只能命中一条。
 * 在一次刷新开始时冻结一次、所有序列复用,即可让网格对齐、tooltip 同时显示多条。
 */
export const freezeTimeValues = (timeValues: TimeValuesProps): TimeValuesProps => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  return { timeRange: [startTime, endTime], originValue: 0 };
};

export const buildPreviousPeriodTimeValues = (timeValues: TimeValuesProps): TimeValuesProps | null => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  if (!startTime || !endTime) return null;
  const duration = endTime - startTime;
  return { timeRange: [startTime - duration, endTime - duration], originValue: 0 };
};
