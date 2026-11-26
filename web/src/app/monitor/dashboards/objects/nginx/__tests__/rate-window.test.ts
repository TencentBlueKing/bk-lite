import { describe, expect, it } from 'vitest';

import { buildSearchParams } from '../../../shared/utils/search-params';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';
import { NGINX_PRO_QUERIES, nginxQueryByKey } from '../queries';
import { nginxCollectionIntervalSeconds } from '../rate-window';
import { buildNginxDashboard, zoneTableLabel, type RangeSeries } from '../layered/model';

const context = { monitorObjectId: 7, instanceId: "('nginx-a',)" };

describe('nginx collection interval', () => {
  it('defaults missing or invalid intervals to 60 seconds', () => {
    expect(nginxCollectionIntervalSeconds()).toBe(60);
    expect(nginxCollectionIntervalSeconds(undefined)).toBe(60);
    expect(nginxCollectionIntervalSeconds(0)).toBe(60);
    expect(nginxCollectionIntervalSeconds(-5)).toBe(60);
    expect(nginxCollectionIntervalSeconds(Number.NaN)).toBe(60);
    expect(nginxCollectionIntervalSeconds(15.2)).toBe(16);
  });

  it('sends that interval as the minimum step and interval_seconds', () => {
    const interval = nginxCollectionIntervalSeconds(undefined);
    const params = buildSearchParams(
      'rate(nginx_requests{__$labels__}[__$rate_window__])',
      'none',
      [],
      [],
      { timeRange: [0, 900_000], originValue: 0 },
      undefined,
      false,
      interval,
      context,
      interval,
    );

    expect(params.interval_seconds).toBe(60);
    expect(params.step).toBe(calculateQueryStep(0, 900_000, 60));
    expect(params.step).toBe(60);
    expect(params.query).toBeUndefined();
  });
});

describe('nginx trend windows and zone totals', () => {
  it('uses the rate window on trend rates and keeps zone * out of listings', () => {
    const rates = NGINX_PRO_QUERIES.filter((item) => item.query.includes('rate('));
    expect(rates.length).toBeGreaterThan(0);
    rates.forEach((item) => {
      expect(item.query).toContain('[__$rate_window__]');
      expect(item.query).not.toContain('[__$window__]');
    });
    expect(nginxQueryByKey('zoneRequestRate')).toContain('zone!="*"');
    expect(nginxQueryByKey('starRequestRate')).toContain('zone="*"');
    expect(nginxQueryByKey('zoneBytes')).toContain('nginx_vts_server_in_bytes');
    expect(nginxQueryByKey('zoneBytes')).not.toContain('bytes_total');
    expect(zoneTableLabel('www.example', false)).toBe('www.example');
    expect(zoneTableLabel('*', true)).toBe('合计');
  });

  it('lists sites without * and uses the zone=* series as the footer total', () => {
    const now = 1_700_000_000;
    const requests = (zone: string, value: number): RangeSeries => ({
      name: 'nginx_vts_server_requests',
      labels: { zone, code: 'total', metric: 'nginx_vts_server_requests' },
      points: [{ time: now, value }]
    });
    const model = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      intervalSeconds: 60,
      data: {
        range: {
          zoneRequestRate: [requests('www', 2), requests('*', 99)],
          starRequestRate: [requests('*', 9)]
        },
        instant: {
          serverFresh: [
            { labels: { metric: 'nginx_vts_server_requests', zone: 'www' }, value: now },
            { labels: { metric: 'nginx_vts_server_requests', zone: '*' }, value: now }
          ]
        }
      }
    });

    expect(model.zoneRows.map((row) => row.zone)).toEqual(['www']);
    expect(model.zoneRequest.map((item) => item.id)).toEqual(['www']);
    expect(model.zoneSummary?.zone).toBe('*');
    expect(model.zoneSummary?.requestRate).toBe(9);
    expect(zoneTableLabel(model.zoneSummary?.zone ?? '', true)).toBe('合计');
  });
});
