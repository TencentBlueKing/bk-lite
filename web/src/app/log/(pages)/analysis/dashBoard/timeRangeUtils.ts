const TARGET_TIME_BUCKETS = 100;
const DEFAULT_QUERY_LIMIT = 100;
const TIME_BUCKET_QUERY_LIMIT = 1000;

const TIME_INTERVALS = [
  { milliseconds: 60 * 1000, value: '1m' },
  { milliseconds: 5 * 60 * 1000, value: '5m' },
  { milliseconds: 10 * 60 * 1000, value: '10m' },
  { milliseconds: 30 * 60 * 1000, value: '30m' },
  { milliseconds: 60 * 60 * 1000, value: '1h' },
  { milliseconds: 2 * 60 * 60 * 1000, value: '2h' },
  { milliseconds: 6 * 60 * 60 * 1000, value: '6h' },
  { milliseconds: 12 * 60 * 60 * 1000, value: '12h' },
  { milliseconds: 24 * 60 * 60 * 1000, value: '1d' },
  { milliseconds: 2 * 24 * 60 * 60 * 1000, value: '2d' },
  { milliseconds: 7 * 24 * 60 * 60 * 1000, value: '7d' },
  { milliseconds: 30 * 24 * 60 * 60 * 1000, value: '30d' }
] as const;

export const calculateLogTimeInterval = (
  startTime: number,
  endTime: number
): string => {
  const duration = Math.abs(endTime - startTime);
  const minimumInterval = duration / TARGET_TIME_BUCKETS;
  const interval = TIME_INTERVALS.find(
    (candidate) => candidate.milliseconds >= minimumInterval
  );

  return (interval || TIME_INTERVALS.at(-1)!).value;
};

export const getDashboardQueryLimit = (query?: string): number =>
  query?.includes('${_time}')
    ? TIME_BUCKET_QUERY_LIMIT
    : DEFAULT_QUERY_LIMIT;
