import assert from 'node:assert/strict';
import test from 'node:test';
import { getChartTypeList } from '../common';
import { resolveDatasourceChartTypes } from '@/app/ops-analysis/components/widgetConfig/utils/tableSettingsBehavior';

test('getChartTypeList includes eventTimeline and radar for datasource selection', () => {
  const values = getChartTypeList().map((item) => item.value);

  assert.ok(values.includes('eventTimeline'));
  assert.ok(values.includes('radar'));
});

test('resolveDatasourceChartTypes returns only datasource-selected chart types', () => {
  const result = resolveDatasourceChartTypes({
    chartTypes: ['line', 'eventTimeline'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'dashboard',
  });

  assert.deepEqual(
    result.map((item) => item.value),
    ['line', 'eventTimeline'],
  );
});

test('resolveDatasourceChartTypes does not inject widget-only chart types', () => {
  const result = resolveDatasourceChartTypes({
    chartTypes: ['line'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'dashboard',
  });

  assert.equal(
    result.some((item) => item.value === 'radar' || item.value === 'eventTimeline'),
    false,
  );
});
