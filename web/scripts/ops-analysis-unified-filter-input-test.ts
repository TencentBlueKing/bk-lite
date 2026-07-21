import assert from 'node:assert/strict';

import { normalizeParamInputChangeValue } from '../src/app/ops-analysis/components/normalizeParamInputChangeValue';
import { processDataSourceParams } from '../src/app/ops-analysis/utils/widgetDataTransform';
import type { UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';

const departmentFilter: UnifiedFilterDefinition = {
  id: 'department__string',
  key: 'department',
  name: '使用部门',
  type: 'string',
  order: 0,
  enabled: true,
};

assert.equal(
  normalizeParamInputChangeValue({ target: { value: '数据部' } }),
  '数据部',
);
assert.equal(normalizeParamInputChangeValue('数据部'), '数据部');
assert.equal(normalizeParamInputChangeValue(''), '');
assert.equal(normalizeParamInputChangeValue(1), 1);
assert.equal(normalizeParamInputChangeValue(null), null);

const buildRequest = (department: string | null) =>
  processDataSourceParams({
    sourceParams: [
      {
        name: 'department',
        alias_name: '使用部门',
        type: 'string',
        filterType: 'filter',
        value: null,
      },
    ],
    unifiedFilterValues: { [departmentFilter.id]: department },
    filterBindings: { [departmentFilter.id]: true },
    filterDefinitions: [departmentFilter],
  });

assert.deepEqual(buildRequest('数据部'), { department: '数据部' });
assert.deepEqual(buildRequest(''), {});
assert.deepEqual(buildRequest(null), {});

console.log('ops analysis unified filter input tests passed');
