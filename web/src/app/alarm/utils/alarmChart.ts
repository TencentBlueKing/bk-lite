import dayjs from 'dayjs';
import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import type { LevelItem } from '@/app/alarm/types/index';

type IntervalUnit = 'second' | 'minute' | 'hour' | 'day';
type ChartBucket = { time: string } & Record<string, string | number>;

const UNIT_MILLISECONDS: Record<IntervalUnit, number> = {
  second: 1000,
  minute: 60 * 1000,
  hour: 60 * 60 * 1000,
  day: 24 * 60 * 60 * 1000,
};

const formatBucketTime = (
  time: dayjs.Dayjs,
  intervalUnit: IntervalUnit,
  convertToLocalizedTime: (iso: string) => string
) => {
  const localTime = convertToLocalizedTime(time.toISOString());
  if (intervalUnit === 'day') return dayjs(localTime).format('YYYY-MM-DD');
  if (intervalUnit === 'hour') {
    return dayjs(localTime).format('YYYY-MM-DD HH:00');
  }
  if (intervalUnit === 'minute') {
    return dayjs(localTime).format('YYYY-MM-DD HH:mm');
  }
  return dayjs(localTime).format('YYYY-MM-DD HH:mm:ss');
};

/**
 * 将告警数据按动态时间区间（秒/分钟/小时/天）分桶，生成适合堆叠柱状图的格式
 * @param data 原始告警列表
 * @param levelList 等级列表，用于初始化各级别统计字段
 * @param convertToLocalizedTime 本地化时间转换函数
 * @param desiredSegments 框定分段数量，默认 12
 */
export function processDataForStackedBarChart(
  data: AlarmTableDataItem[],
  levelList: LevelItem[],
  convertToLocalizedTime: (iso: string) => string,
  desiredSegments = 12
) {
  if (!data?.length) return [];

  // 表格的时间筛选和排序均以 created_at 为准，图表也使用同一时间口径。
  const validData = data.filter((item) => dayjs(item.created_at).isValid());
  if (!validData.length) return [];

  const timestamps = validData.map((item) => dayjs(item.created_at));
  const minTime = timestamps.reduce(
    (min, cur) => (cur.isBefore(min) ? cur : min),
    timestamps[0]
  );
  const maxTime = timestamps.reduce(
    (max, cur) => (cur.isAfter(max) ? cur : max),
    timestamps[0]
  );

  const segmentTarget = Math.max(1, desiredSegments);
  const totalMilliseconds = maxTime.valueOf() - minTime.valueOf();
  const rawIntervalMilliseconds = Math.max(
    UNIT_MILLISECONDS.second,
    totalMilliseconds / segmentTarget
  );
  const intervalUnit: IntervalUnit =
    rawIntervalMilliseconds < UNIT_MILLISECONDS.minute
      ? 'second'
      : rawIntervalMilliseconds < UNIT_MILLISECONDS.hour
        ? 'minute'
        : rawIntervalMilliseconds < UNIT_MILLISECONDS.day
          ? 'hour'
          : 'day';
  const intervalCount = Math.max(
    1,
    Math.ceil(rawIntervalMilliseconds / UNIT_MILLISECONDS[intervalUnit])
  );
  const totalUnits = maxTime.diff(minTime, intervalUnit, true);
  const segmentsCount = Math.floor(totalUnits / intervalCount) + 1;
  const buckets: ChartBucket[] = Array.from(
    { length: segmentsCount },
    (_, index) => {
      const bucketTime = minTime.add(index * intervalCount, intervalUnit);
      const time = formatBucketTime(
        bucketTime,
        intervalUnit,
        convertToLocalizedTime
      );
      return {
        time,
        ...levelList.reduce(
          (acc, level) => {
            acc[level.level_display_name] = 0;
            return acc;
          },
          {} as Record<string, number>
        ),
      };
    }
  );

  validData.forEach((item) => {
    const bucketIndex = Math.floor(
      dayjs(item.created_at).diff(minTime, intervalUnit, true) / intervalCount
    );
    const level = levelList.find(
      (itemLevel) => itemLevel.level_id === Number(item.level)
    );
    const bucket = buckets[bucketIndex];
    if (level && bucket) {
      bucket[level.level_display_name] =
        Number(bucket[level.level_display_name] || 0) + 1;
    }
  });

  return buckets;
}
