import dayjs from 'dayjs';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';
import { afterEach, describe, expect, it } from 'vitest';

import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';

dayjs.extend(utc);
dayjs.extend(timezone);

const UNIX_SAMPLES = [
  1700000000,
  1710050400,
  1710432000,
  1710460800,
  1721001600,
  1735689600,
];

const expectedUnixLabel = (seconds: number, timezoneName: string) => {
  const millis = seconds * 1000;
  const local = dayjs(millis);
  const format = local.hour() === 0 && local.minute() === 0 && local.second() === 0
    ? 'YYYY-MM-DD'
    : 'MM-DD HH:mm';
  return dayjs(millis).tz(timezoneName).format(format);
};

afterEach(() => {
  window.localStorage.removeItem('timezone');
});

describe('ChartDataTransformer.formatTimeValue', () => {
  it.each(['Asia/Shanghai', 'America/New_York'])(
    'matches the uncached timezone label in %s, including repeated timestamps',
    (timezoneName) => {
      window.localStorage.setItem('timezone', timezoneName);

      UNIX_SAMPLES.forEach((seconds) => {
        const expected = expectedUnixLabel(seconds, timezoneName);
        expect(ChartDataTransformer.formatTimeValue(seconds)).toBe(expected);
        expect(ChartDataTransformer.formatTimeValue(String(seconds))).toBe(expected);
        expect(ChartDataTransformer.formatTimeValue(seconds)).toBe(expected);
      });
    },
  );

  it('does not reuse a label after the stored timezone changes', () => {
    const seconds = 1721001600;
    window.localStorage.setItem('timezone', 'Asia/Shanghai');
    const shanghai = ChartDataTransformer.formatTimeValue(seconds);
    window.localStorage.setItem('timezone', 'America/New_York');
    const newYork = ChartDataTransformer.formatTimeValue(seconds);

    expect(shanghai).toBe(expectedUnixLabel(seconds, 'Asia/Shanghai'));
    expect(newYork).toBe(expectedUnixLabel(seconds, 'America/New_York'));
    expect(newYork).not.toBe(shanghai);
  });

  it('formats a shared time axis once per timestamp across series', () => {
    window.localStorage.setItem('timezone', 'Asia/Shanghai');
    const start = 1710460800;
    const points = Array.from({ length: 4 }, (_, index) => [start + index * 900, index]);
    const rawData = Object.fromEntries(
      ['cpu', 'mem', 'disk'].map((name) => [name, points.map(([time, value]) => [time, value])]),
    );

    const transformed = ChartDataTransformer.transformToLineBarData(rawData);
    const labels = points
      .map(([time]) => expectedUnixLabel(time as number, 'Asia/Shanghai'))
      .sort();

    expect(transformed.categories).toEqual(labels);
    expect(transformed.series?.every((series) => series.data.length === labels.length)).toBe(true);
  });
});
