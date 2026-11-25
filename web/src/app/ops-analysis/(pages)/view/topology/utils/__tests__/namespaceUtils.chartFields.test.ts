import assert from 'node:assert/strict';
import test from 'node:test';
import type { WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
import { buildValueConfig } from '../namespaceUtils';

const saved = (values: WidgetConfig) => buildValueConfig(values);

test('topology bar save keeps the dimension and value fields', () => {
  const config = saved({
    name: '监控实例分布',
    chartType: 'bar',
    dataSource: 12,
    dimensionField: 'instance_count',
    valueField: 'instance_count',
    valueFields: ['instance_count'],
    displayLimit: 5,
    sortByValue: true,
  });

  assert.equal(config.dimensionField, 'instance_count');
  assert.equal(config.valueField, 'instance_count');
  assert.deepEqual(config.valueFields, ['instance_count']);
  assert.equal(config.displayLimit, 5);
  assert.equal(config.sortByValue, true);
});

test('topology line save keeps a series split', () => {
  const config = saved({
    name: '趋势',
    chartType: 'line',
    dimensionField: 'time',
    seriesField: 'host',
    valueField: 'cpu',
  });

  assert.equal(config.dimensionField, 'time');
  assert.equal(config.seriesField, 'host');
  assert.equal(config.valueField, 'cpu');
});

test('topology pie save keeps slices and scalar fields', () => {
  const config = saved({
    name: '占比',
    chartType: 'pie',
    dimensionField: 'name',
    valueField: 'count',
    pieScalarFields: [
      { field: 'used', label: '已用' },
      { field: 'free', label: '空闲' },
    ],
  });

  assert.equal(config.dimensionField, 'name');
  assert.equal(config.valueField, 'count');
  assert.deepEqual(config.pieScalarFields, [
    { field: 'used', label: '已用' },
    { field: 'free', label: '空闲' },
  ]);
});

test('topology multi value, timeline, radar and card list keep their field config', () => {
  const multiValue = saved({
    name: '多值',
    chartType: 'multiValue',
    multiValueLabelField: 'name',
    multiValueValueField: 'count',
  });
  const timeline = saved({
    name: '事件',
    chartType: 'eventTimeline',
    eventTimeline: { timeField: 'time', titleField: 'title', sortOrder: 'desc' },
  });
  const radar = saved({
    name: '雷达',
    chartType: 'radar',
    radar: { indicators: [{ key: 'cpu', label: 'CPU' }] },
  });
  const cards = saved({
    name: '卡片',
    chartType: 'cardList',
    cardList: { titleField: 'name', layout: 'list' },
  });

  assert.equal(multiValue.multiValueLabelField, 'name');
  assert.equal(multiValue.multiValueValueField, 'count');
  assert.deepEqual(timeline.eventTimeline, {
    timeField: 'time',
    titleField: 'title',
    sortOrder: 'desc',
  });
  assert.deepEqual(radar.radar, { indicators: [{ key: 'cpu', label: 'CPU' }] });
  assert.deepEqual(cards.cardList, { titleField: 'name', layout: 'list' });
});

test('topology scene widget save keeps the scene payload', () => {
  const config = saved({
    name: '关联拓扑',
    chartType: 'relatedTopology',
    sceneWidgetType: 'relatedTopology',
    relatedTopology: { modelId: 'host', instUuid: 'abc' },
  });

  assert.equal(config.sceneWidgetType, 'relatedTopology');
  assert.deepEqual(config.relatedTopology, { modelId: 'host', instUuid: 'abc' });
});

test('topology gauge save keeps compare and value mappings', () => {
  const config = saved({
    name: '仪表',
    chartType: 'gauge',
    compare: true,
    compareMode: 'value',
    valueMappings: [{ type: 'value', value: '1', result: { text: '开' } }],
  });

  assert.equal(config.compare, true);
  assert.equal(config.compareMode, 'value');
  assert.deepEqual(config.valueMappings, [{ type: 'value', value: '1', result: { text: '开' } }]);
});
