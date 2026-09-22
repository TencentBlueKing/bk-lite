import { describe, expect, it } from 'vitest';

import { buildMetricCatalogLines, metricCatalogSections } from '../metricCatalog';

describe('metricCatalog', () => {
  const groups = [
    {
      display_name: '磁盘',
      child: [
        {
          name: 'disk_used_percent',
          display_name: '磁盘使用率',
          unit: '%',
          viewData: [
            { time: 1_704_067_200, value1: 71 },
            { time: 1_704_067_260, value1: 82.9 },
          ],
        },
        { name: 'disk_io', display_name: '磁盘吞吐' },
      ],
    },
  ];

  it('lists every metric and only serializes loaded series', () => {
    const built = buildMetricCatalogLines(groups);
    expect(built.catalog).toContain('磁盘使用率 (disk_used_percent)');
    expect(built.catalog).toContain('磁盘吞吐 (disk_io, 未加载)');
    expect(built.loaded).toBe(1);
    expect(built.total).toBe(2);
    expect(built.series).toHaveLength(1);
    expect(built.series[0].name).toBe('磁盘使用率');
    expect(built.series[0].value?.length).toBeGreaterThan(0);
    const sections = metricCatalogSections(built, ['正在查看全量指标']);
    expect(sections.some((section) => section.id === 'metric-catalog')).toBe(true);
    expect(sections.some((section) => section.id === 'metric-series')).toBe(true);
    expect(sections.some((section) => section.content.includes('还有 1 个未加载'))).toBe(true);
  });
});
