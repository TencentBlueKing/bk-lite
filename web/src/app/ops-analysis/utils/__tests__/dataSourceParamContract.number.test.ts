import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import type { UnifiedFilterDefinition } from '../../types/dashBoard';
import { isBindableDataSourceParamType } from '../dataSourceParamContract';
import { buildResetFilterValues } from '../unifiedFilterState';
import { getBindableFilterParams } from '../widgetDataTransform';

test('number is bindable for unified filter', () => {
  assert.equal(isBindableDataSourceParamType('number'), true);
  assert.equal(isBindableDataSourceParamType('boolean'), false);
});

test('getBindableFilterParams picks up number + filterType=filter', () => {
  const params = getBindableFilterParams([
    {
      name: 'cpu_idle_min',
      alias_name: 'CPU 空闲',
      type: 'number',
      filterType: 'filter',
      value: -1,
    },
    {
      name: 'enabled',
      alias_name: '启用',
      type: 'boolean',
      filterType: 'filter',
      value: true,
    },
    {
      name: 'limit',
      alias_name: '条数',
      type: 'number',
      filterType: 'params',
      value: 10,
    },
  ]);

  assert.deepEqual(
    params.map(({ name, type }) => ({ name, type })),
    [{ name: 'cpu_idle_min', type: 'number' }],
  );
});

test('reset keeps numeric default including -1', () => {
  const definition: UnifiedFilterDefinition = {
    id: 'cpu_idle_min__number',
    key: 'cpu_idle_min',
    name: 'CPU 空闲',
    type: 'number',
    defaultValue: -1,
    order: 0,
    enabled: true,
  };

  assert.deepEqual(buildResetFilterValues([definition]), {
    cpu_idle_min__number: -1,
  });
});

test('unified filter bar renders number with InputNumber and numeric values', () => {
  const filterBarSource = readFileSync(
    fileURLToPath(
      new URL(
        '../../components/unifiedFilter/unifiedFilterBar.tsx',
        import.meta.url,
      ),
    ),
    'utf8',
  );

  assert.match(filterBarSource, /case ['"]number['"]/);
  assert.match(
    filterBarSource,
    /case ['"]number['"][\s\S]{0,500}<InputNumber/,
  );
  assert.doesNotMatch(
    filterBarSource,
    /case ['"]number['"][\s\S]{0,800}\.join\(/,
  );
});
