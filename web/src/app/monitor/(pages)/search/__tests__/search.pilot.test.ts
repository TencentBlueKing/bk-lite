import { afterEach, describe, expect, it } from 'vitest';

import type { PageContextToolkit } from '@/components/ai-page-context/types';
import type { ChartItem, SearchPayload } from '@/app/monitor/types/search';
import {
  getContext,
  getTextContext,
  publishSearchSnapshot,
  summarizeSearchForm,
} from '../search.pilot';

const stubToolkit = (images: Array<{ caption: string; dataUrl: string }>): PageContextToolkit => ({
  captureEchartsFromDoms: async () => [],
  captureEchartsFromDom: async () => [],
  captionFromOption: () => '',
  captureRechartsFromDoms: async () => images,
});

const payload = {
  activeGroup: {
    id: 'g1',
    name: '查询条件 1',
    object: '1',
    plugin: '2',
    instanceIds: ['web-1'],
    metric: '9',
    aggregation: 'avg',
    conditions: [{ label: 'mount', condition: '=', value: '/' }],
    collapsed: false,
  },
  queryGroups: [],
  metricsMap: { 2: [{ id: 9, name: 'disk_used_percent', display_name: '磁盘使用率' }] },
  instancesMap: { 1: [{ instance_id: 'web-1', instance_name: 'web-1', instance_id_values: ['web-1'] }] },
  pluginsMap: { 1: [{ id: '2', name: 'Host', display_name: 'Host' }] },
  objectsMap: { 1: { id: 1, name: 'Host', display_name: '主机' } },
} as unknown as SearchPayload;

const chart = (name: string): ChartItem => ({
  groupId: name,
  groupName: name,
  metric: { id: 1, name, display_name: name } as ChartItem['metric'],
  data: [{ time: 1_704_067_200, value1: 1 } as never],
  unit: '%',
  loading: false,
  duration: 1,
  objectName: 'Host',
  aggregation: 'avg',
});

describe('search.pilot', () => {
  afterEach(() => {
    publishSearchSnapshot(null);
    document.body.innerHTML = '';
  });

  it('summarizes the form and has no charts before search', () => {
    publishSearchSnapshot({ payload, charts: [] });
    const form = summarizeSearchForm(payload, '最近15分钟');
    expect(form.join('\n')).toContain('对象:');
    expect(form.join('\n')).toContain('磁盘使用率');
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看指标搜索');
    expect(text).toContain('磁盘使用率');
    expect(getTextContext().images || []).toEqual([]);
  });

  it('captures screenshots when there are 3 charts', async () => {
    publishSearchSnapshot({ payload, charts: [chart('a'), chart('b'), chart('c')] });
    const full = await getContext(stubToolkit([
      { caption: 'a', dataUrl: 'data:image/jpeg,1' },
      { caption: 'b', dataUrl: 'data:image/jpeg,2' },
      { caption: 'c', dataUrl: 'data:image/jpeg,3' },
    ]));
    expect(full.images).toHaveLength(3);
    expect((full.sections || []).some((section) => section.id === 'metric-series')).toBe(false);
  });

  it('uses JSON and no images when there are 7 charts', async () => {
    const charts = Array.from({ length: 7 }, (_, index) => chart(`m${index}`));
    publishSearchSnapshot({ payload, charts });
    const full = await getContext(stubToolkit([{ caption: 'no', dataUrl: 'data:image/jpeg,x' }]));
    expect(full.images || []).toEqual([]);
    const series = (full.sections || []).find((section) => section.id === 'metric-series')?.content || '';
    expect(series).toContain('m0');
    expect(series).toContain('"value"');
  });
});
