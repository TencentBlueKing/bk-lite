import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { extractComparableValue, validateGaugeData } from '@/app/ops-analysis/utils/compareQuery';
import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';
import { parseCardListItems } from '@/app/ops-analysis/utils/cardList';
import { buildTopNItems } from '@/app/ops-analysis/utils/topNData';
import { validateMultiValueData } from '@/app/ops-analysis/utils/multiValueData';
import { resolveRadarSeriesData } from '@/app/ops-analysis/utils/radarData';
import { parseEventTimelineItems, validateEventTimelinePayload } from '@/app/ops-analysis/utils/eventTimeline';
import { buildNodeGraph } from '@/app/ops-analysis/utils/nodeGraphData';

// REST、数据库、Excel 运行时均把连接器结果的 items 交给组件；列名由用户定义。
const rows = [
  { resource_name: 'MySQL', resource_count: 18, occurred_at: '2026-10-22T01:00:00Z', client: '10.0.0.1', server: '10.0.0.2' },
  { resource_name: 'Oracle', resource_count: '0', occurred_at: '2026-10-22T02:00:00Z', client: '10.0.0.1', server: '10.0.0.3' },
  { resource_name: 'Redis', resource_count: '6', occurred_at: '2026-10-22T03:00:00Z', client: '10.0.0.2', server: '10.0.0.3' },
];
const labels = ['MySQL', 'Oracle', 'Redis'];
const values = [18, 0, 6];
const mapping = { dimensionField: 'resource_name', valueField: 'resource_count' };

describe('connector record arrays across supported charts', () => {
  it('uses the same rows for tables, event tables and mapped cards', () => {
    const table = parseTableLikeData(rows, { current: 1, pageSize: 20 });
    assert.deepEqual(table.rows, rows);
    const cards = parseCardListItems(rows, { titleField: 'resource_name', badgeField: 'resource_count' });
    assert.equal(cards.status, 'ready');
    assert.deepEqual(cards.items.map((card) => card.primary), labels);
    assert.deepEqual(cards.items.map((card) => card.badge), ['18', '0', '6']);
  });

  it('uses existing name/value and name/count record columns for line and bar', () => {
    const namedValues = [
      { name: 'MySQL', value: 18 },
      { name: 'Oracle', value: '0' },
      { name: 'Redis', value: '6' },
    ];
    const namedCounts = [
      { name: 'MySQL', count: 18 },
      { name: 'Oracle', count: 0 },
      { name: 'Redis', count: 6 },
    ];
    for (const payload of [namedValues, namedCounts]) {
      assert.equal(ChartDataTransformer.validateLineBarData(payload).isValid, true);
      const lineBar = ChartDataTransformer.transformToLineBarData(payload);
      assert.deepEqual(lineBar.categories, labels);
      assert.deepEqual(lineBar.values, values);
    }
    // 折线/柱状配置目前不保存任意字段映射，业务列名不能假定可自动识别。
    assert.equal(ChartDataTransformer.validateLineBarData(rows).isValid, false);
  });

  it('maps arbitrary name and numeric columns to pie charts', () => {
    assert.equal(ChartDataTransformer.validatePieData(rows, 'invalid', mapping).isValid, true);
    const pie = ChartDataTransformer.transformToPieData(rows, mapping);
    assert.deepEqual(pie.map((slice) => slice.name), labels);
    assert.deepEqual(pie.map((slice) => slice.value), values);
  });

  it('maps arbitrary columns to ranking, multi-value and radar components', () => {
    const top = buildTopNItems(rows, 'resource_name', 'resource_count');
    assert.deepEqual(top.map((item) => item.name), ['MySQL', 'Redis', 'Oracle']);
    assert.deepEqual(top.map((item) => item.value), [18, 6, 0]);
    const multi = validateMultiValueData(rows, 'invalid', { labelField: 'resource_name', valueField: 'resource_count' });
    assert.equal(multi.isValid, true);
    assert.deepEqual(multi.items, labels.map((label, index) => ({ label, value: String(values[index]) })));
    const radar = resolveRadarSeriesData(rows, { arrayNameField: 'resource_name', arrayValueField: 'resource_count' });
    assert.deepEqual(radar.indicatorLabels, labels);
    assert.deepEqual(radar.indicatorValues, values);
  });

  it('maps timestamp/title and source/target/value columns without changing the payload', () => {
    const timelineMapping = { timeField: 'occurred_at', titleField: 'resource_name' };
    assert.equal(validateEventTimelinePayload(rows, timelineMapping).isValid, true);
    const timeline = parseEventTimelineItems(rows, { ...timelineMapping, sortOrder: 'asc' });
    assert.deepEqual(timeline.items.map((item) => item.title), labels);
    const graph = buildNodeGraph(rows, { sourceField: 'client', targetField: 'server', valueField: 'resource_count' });
    assert.deepEqual(graph.edges, [
      { source: '10.0.0.1', target: '10.0.0.2', value: 18 },
      { source: '10.0.0.2', target: '10.0.0.3', value: 6 },
      { source: '10.0.0.1', target: '10.0.0.3', value: 0 },
    ]);
  });

  it('single and gauge read the first selected cell rather than summing records', () => {
    assert.equal(extractComparableValue(rows, 'resource_count'), 18);
    assert.equal(validateGaugeData(rows, { selectedFields: ['resource_count'] }).isValid, true);
    assert.equal(extractComparableValue(rows.slice(1), 'resource_count'), '0');
    assert.equal(extractComparableValue(rows, 'missing'), null);
  });
});
