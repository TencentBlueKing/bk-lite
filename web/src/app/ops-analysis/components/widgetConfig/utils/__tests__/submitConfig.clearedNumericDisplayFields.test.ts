import assert from 'node:assert/strict';
import test from 'node:test';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  buildWidgetSubmitConfig,
  mergeSanitizedWidgetValueConfig,
} from '../submitConfig';
import { formatDisplayValue as formatDashboardDisplayValue } from '@/app/ops-analysis/utils/thresholdUtils';
import { formatDisplayValue as formatWidgetDisplayValue } from '@/app/ops-analysis/components/ops-analysis-config-sections';
import { formatDisplayValue as formatTopologyDisplayValue } from '@/app/ops-analysis/(pages)/view/topology/utils/topologyUtils';

const baseInput = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: ['cpu'],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
} as const;

const existingValueConfig: ValueConfig = {
  name: 'CPU',
  chartType: 'single',
  selectedFields: ['cpu'],
  conversionFactor: 100,
  decimalPlaces: 2,
};

const persistClearedNumericFields = (
  chartType: 'single' | 'gauge',
  existing: ValueConfig,
) => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: 'CPU',
      chartType,
      // Ant Design InputNumber 清空后提交 null，而不是 undefined
      conversionFactor: null as unknown as number,
      decimalPlaces: null as unknown as number,
    },
    chartType,
  });

  assert.equal(submitted.error, undefined);
  assert.ok(submitted.config);

  return mergeSanitizedWidgetValueConfig(
    existing,
    {
      chartType,
      conversionFactor: submitted.config?.conversionFactor,
      decimalPlaces: submitted.config?.decimalPlaces,
    },
    chartType,
  );
};

test('clearing conversionFactor and decimalPlaces on single does not persist null', () => {
  const persisted = persistClearedNumericFields('single', existingValueConfig);

  assert.equal('conversionFactor' in persisted, false);
  assert.equal('decimalPlaces' in persisted, false);
});

test('clearing conversionFactor and decimalPlaces on gauge does not persist null', () => {
  const persisted = persistClearedNumericFields('gauge', {
    ...existingValueConfig,
    chartType: 'gauge',
  });

  assert.equal('conversionFactor' in persisted, false);
  assert.equal('decimalPlaces' in persisted, false);
});

test('explicit zero decimalPlaces is still persisted', () => {
  const submitted = buildWidgetSubmitConfig({
    ...baseInput,
    values: {
      name: 'CPU',
      chartType: 'single',
      conversionFactor: 10,
      decimalPlaces: 0,
    },
    chartType: 'single',
  });

  assert.equal(submitted.config?.conversionFactor, 10);
  assert.equal(submitted.config?.decimalPlaces, 0);
});

const displayFormatters = [
  ['dashboard widgets', formatDashboardDisplayValue],
  ['ops-analysis widgets', formatWidgetDisplayValue],
  ['topology nodes', formatTopologyDisplayValue],
] as const;

for (const [label, formatDisplayValue] of displayFormatters) {
  test(`${label}: cleared conversionFactor does not turn the value into 0`, () => {
    const text = formatDisplayValue(
      12.34,
      undefined,
      undefined,
      null as unknown as number,
    );
    assert.equal(text, formatDisplayValue(12.34));
    assert.notEqual(text, '0');
  });

  test(`${label}: cleared decimalPlaces restores default instead of 0 places`, () => {
    const text = formatDisplayValue(
      12.34,
      undefined,
      null as unknown as number,
    );
    assert.equal(text, formatDisplayValue(12.34));
    assert.notEqual(text, '12');
  });
}
