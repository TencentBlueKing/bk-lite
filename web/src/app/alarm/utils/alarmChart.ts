import dayjs from 'dayjs';
import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import type { LevelItem } from '@/app/alarm/types/index';

type BucketUnit = 'day' | 'month';
type ChartBucket = { time: string } & Record<string, string | number>;

const DAILY_BUCKET_MAX_SPAN_DAYS = 180;

export function getChartAxisTicks(
  data: Array<{ time?: unknown }>,
  maxTicks = 12
): string[] {
  const times = data
    .map(({ time }) => time)
    .filter((time): time is string => typeof time === 'string');
  const tickLimit = Math.max(2, Math.floor(maxTicks));

  if (times.length <= tickLimit) return times;

  const lastIndex = times.length - 1;
  return Array.from(
    { length: tickLimit },
    (_, index) => times[Math.round((index * lastIndex) / (tickLimit - 1))]
  );
}

/**
 * 将告警数据按 created_at 所在的自然日或自然月分桶，生成适合堆叠柱状图的格式
 * @param data 原始告警列表
 * @param levelList 等级列表，用于初始化各级别统计字段
 * @param convertToLocalizedTime 本地化时间转换函数
 */
export function processDataForStackedBarChart(
  data: AlarmTableDataItem[],
  levelList: LevelItem[],
  convertToLocalizedTime: (iso: string) => string
) {
  if (!data?.length) return [];

  // 表格的时间筛选和排序均以 created_at 为准，图表也使用同一时间口径。
  const validData = data
    .map((item) => ({
      item,
      localCreatedAt: dayjs(convertToLocalizedTime(item.created_at)),
    }))
    .filter(({ localCreatedAt }) => localCreatedAt.isValid());
  if (!validData.length) return [];

  const timestamps = validData.map(({ localCreatedAt }) => localCreatedAt);
  const earliestTime = timestamps.reduce(
    (min, cur) => (cur.isBefore(min) ? cur : min),
    timestamps[0]
  );
  const latestTime = timestamps.reduce(
    (max, cur) => (cur.isAfter(max) ? cur : max),
    timestamps[0]
  );

  const daySpan = latestTime
    .startOf('day')
    .diff(earliestTime.startOf('day'), 'day');
  const bucketUnit: BucketUnit =
    daySpan <= DAILY_BUCKET_MAX_SPAN_DAYS ? 'day' : 'month';
  const bucketFormat = bucketUnit === 'day' ? 'YYYY-MM-DD' : 'YYYY-MM';
  const minTime = earliestTime.startOf(bucketUnit);
  const maxTime = latestTime.startOf(bucketUnit);

  const segmentsCount = maxTime.diff(minTime, bucketUnit) + 1;
  const buckets: ChartBucket[] = Array.from(
    { length: segmentsCount },
    (_, index) => {
      const time = minTime.add(index, bucketUnit).format(bucketFormat);
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

  validData.forEach(({ item, localCreatedAt }) => {
    const bucketIndex = localCreatedAt
      .startOf(bucketUnit)
      .diff(minTime, bucketUnit);
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
