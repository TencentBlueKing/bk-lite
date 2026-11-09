import { describe, expect, it } from 'vitest';

import { formatMetricValue } from '@/app/monitor/dashboards/shared/utils/format';
import {
  classicRedisHitRateDisplay,
  redisShownHitPercent,
  redisWindowKeyspace,
  scaleRatioToPercent,
  type RedisMetricMap
} from '../series';

const series = (points: Array<[number, number]>) => ({
  loadState: 'success' as const,
  viewData: points.map(([time, value1]) => ({ time, value1 }))
});

const metricMap = (entries: Record<string, Array<[number, number]>>): RedisMetricMap => (
  Object.fromEntries(Object.entries(entries).map(([name, points]) => [name, series(points)])) as RedisMetricMap
);

describe('redis window hit rate and penetration', () => {
  it('uses the same window hits and misses so the two percents sum to 100', () => {
    const map = metricMap({
      redis_keyspace_hits_rate: [[10, 8]],
      redis_keyspace_misses_rate: [[10, 2]],
      redis_keyspace_hitrate: [[10, 0.99]]
    });
    const shown = redisShownHitPercent(map, null, true);
    const keyspace = shown.keyspace;
    expect(shown.fallback).toBe(false);
    expect(shown.percent).toBe(80);
    expect(keyspace.penetrationPercent).toBe(20);
    expect((shown.percent ?? 0) + (keyspace.penetrationPercent ?? 0)).toBe(100);
    expect(keyspace.points.at(-1)?.value1).toBe(80);
  });

  it('still sums to 100 when the latest hit and miss samples are not the same timestamp', () => {
    const keyspace = redisWindowKeyspace(metricMap({
      redis_keyspace_hits_rate: [[1, 9]],
      redis_keyspace_misses_rate: [[2, 1]]
    }), null);
    expect(keyspace.hitPercent).toBe(90);
    expect(keyspace.penetrationPercent).toBe(10);
    expect(keyspace.points.at(-1)).toEqual({ time: 2, value1: 90 });
  });

  it('rounds the pair so one decimal place still sums to 100', () => {
    const keyspace = redisWindowKeyspace(metricMap({
      redis_keyspace_hits_rate: [[10, 1]],
      redis_keyspace_misses_rate: [[10, 2]]
    }), null);
    expect(keyspace.hitPercent).toBe(33.3);
    expect(keyspace.penetrationPercent).toBe(66.7);
    expect((keyspace.hitPercent ?? 0) + (keyspace.penetrationPercent ?? 0)).toBe(100);
  });

  it('keeps 0/0 empty instead of falling back to the lifetime gauge', () => {
    const shown = redisShownHitPercent(metricMap({
      redis_keyspace_hits_rate: [[10, 0]],
      redis_keyspace_misses_rate: [[10, 0]],
      redis_keyspace_hitrate: [[10, 0.99]]
    }), null, true);
    expect(shown.keyspace.bothKnown).toBe(true);
    expect(shown.percent).toBeNull();
    expect(shown.fallback).toBe(false);
    expect(shown.keyspace.penetrationPercent).toBeNull();
  });

  it('uses the lifetime gauge only when the window has no paired samples', () => {
    const shown = redisShownHitPercent(metricMap({
      redis_keyspace_hitrate: [[10, 0.94]]
    }), null, true);
    expect(shown.fallback).toBe(true);
    expect(shown.percent).toBe(94);
    expect(shown.keyspace.penetrationPercent).toBeNull();
  });

  it('does not show the lifetime gauge while window samples are still pending', () => {
    const shown = redisShownHitPercent(metricMap({
      redis_keyspace_hitrate: [[10, 0.94]]
    }), null, false);
    expect(shown.fallback).toBe(false);
    expect(shown.percent).toBeNull();
  });

  it('turns a 0-1 classic reading into a real percent', () => {
    expect(formatMetricValue(0.94, 'percent')).toEqual({ value: '0.9', unit: '%' });
    expect(scaleRatioToPercent(0.94)).toBeCloseTo(94);
    expect(scaleRatioToPercent(94)).toBe(94);
    expect(classicRedisHitRateDisplay([{ time: 10, value1: 0.94 }])).toEqual({ value: '94.0', unit: '%' });
  });
});
