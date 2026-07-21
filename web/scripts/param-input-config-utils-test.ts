import assert from 'node:assert/strict';
import {
  extractDataSourceItems,
  mapDynamicItems,
  normalizeInputConfig,
  resolveDynamicSourceId,
} from '../src/app/ops-analysis/utils/paramInputConfigUtils';

const staticOptions = [
  { label: '机房A', value: 1 },
  { label: '机房B', value: '2' },
];

assert.deepEqual(
  normalizeInputConfig({
    inputConfig: { control: 'input' },
  }),
  { control: 'input' },
);

assert.deepEqual(
  normalizeInputConfig({
    options: staticOptions,
  }),
  {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: staticOptions,
    },
  },
);

assert.equal(normalizeInputConfig({}), undefined);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceId: 12,
      valueField: '_id',
      labelField: 'inst_name',
    },
    [],
  ),
  12,
);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/get_room_list' },
      valueField: '_id',
      labelField: 'inst_name',
    },
    [
      { id: 8, rest_api: 'monitor/query' },
      { id: 9, rest_api: 'cmdb/get_room_list' },
    ],
  ),
  9,
);

assert.equal(
  resolveDynamicSourceId(
    {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/missing' },
      valueField: '_id',
      labelField: 'inst_name',
    },
    [{ id: 9, rest_api: 'cmdb/get_room_list' }],
  ),
  undefined,
);

assert.deepEqual(extractDataSourceItems({ items: [{ _id: 1 }] }), [{ _id: 1 }]);
assert.deepEqual(extractDataSourceItems({ data: { items: [{ _id: 2 }] } }), [{ _id: 2 }]);
assert.deepEqual(extractDataSourceItems([{ _id: 3 }]), [{ _id: 3 }]);
assert.deepEqual(extractDataSourceItems({ data: null }), []);

assert.deepEqual(
  mapDynamicItems(
    [
      null,
      '非对象项',
      { _id: 1, inst_name: '机房A' },
      { _id: undefined, inst_name: '无ID' },
      { _id: 2, inst_name: null },
    ] as unknown as Record<string, unknown>[],
    '_id',
    'inst_name',
  ),
  [
    { value: 1, label: '机房A' },
    { value: 2, label: '' },
  ],
);

console.log('✓ param-input-config-utils-test.ts 全部通过');
