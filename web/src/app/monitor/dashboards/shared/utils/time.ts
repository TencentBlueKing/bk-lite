import { TimeValuesProps } from '@/app/monitor/types';
import { getRecentTimeRange } from '@/app/monitor/utils/common';

export const buildPreviousPeriodTimeValues = (timeValues: TimeValuesProps): TimeValuesProps | null => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  if (!startTime || !endTime) return null;
  const duration = endTime - startTime;
  return { timeRange: [startTime - duration, endTime - duration], originValue: 0 };
};
