import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import { getChartTypeList } from '../common';
import { resolveDatasourceChartTypes } from '@/app/ops-analysis/components/widgetConfig/utils/tableSettingsBehavior';
import { REPORT_CHART_TYPES } from '@/app/ops-analysis/utils/chartTypeSurface';

test('getChartTypeList includes datasource-driven chart types', () => {
  const values = getChartTypeList().map((item) => item.value);

  assert.ok(values.includes('eventTimeline'));
  assert.ok(values.includes('radar'));
  assert.ok(values.includes('cardList'));
  assert.ok(values.includes('topologyMap'));
  assert.ok(values.includes('nodeGraph'));
});

test('report surface does not expose nodeGraph even when the datasource declares it', () => {
  const result = resolveDatasourceChartTypes({
    chartTypes: ['table', 'nodeGraph'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'report',
  });

  assert.deepEqual(
    result.map((item) => item.value),
    ['table'],
  );
});

test('resolveDatasourceChartTypes exposes topologyMap only when declared by datasource', () => {
  const supported = resolveDatasourceChartTypes({
    chartTypes: ['line', 'topologyMap'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'dashboard',
  });
  const unsupported = resolveDatasourceChartTypes({
    chartTypes: ['line'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'dashboard',
  });

  assert.deepEqual(
    supported.map((item) => item.value),
    ['line', 'topologyMap'],
  );
  assert.equal(
    unsupported.some((item) => item.value === 'topologyMap'),
    false,
  );
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
    result.some(
      (item) =>
        item.value === 'radar' ||
        item.value === 'eventTimeline' ||
        item.value === 'cardList',
    ),
    false,
  );
});

test('report surface exposes only registered table component types', () => {
  const result = resolveDatasourceChartTypes({
    chartTypes: ['line', 'table', 'eventTable', 'cardList'],
    chartTypeDefinitions: getChartTypeList(),
    surface: 'report',
  });

  assert.deepEqual(
    result.map((item) => item.value),
    ['table', 'eventTable'],
  );
});

test('frontend and backend report component registries expose the same types', () => {
  const backendSource = readFileSync(
    resolve(process.cwd(), '../server/apps/operation_analysis/services/report_view_sets.py'),
    'utf8',
  );
  const registryMatch = backendSource.match(/REPORT_COMPONENT_TYPES = frozenset\(\{([^}]+)\}\)/);
  assert.ok(registryMatch, 'backend report component registry must remain discoverable');
  const backendTypes = Array.from(registryMatch[1].matchAll(/["']([^"']+)["']/g), (match) => match[1]).sort();

  const frontendTypes = Array.from(REPORT_CHART_TYPES).sort();

  assert.deepEqual(frontendTypes, backendTypes);
});
