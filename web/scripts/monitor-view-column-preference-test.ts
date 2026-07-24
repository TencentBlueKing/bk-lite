import assert from 'node:assert/strict';

import { resolveViewColumns } from '../src/app/monitor/(pages)/view/viewColumnPreference';

const available = [
  { key: 'instance_name', title: '名称' },
  { key: 'time', title: '上报时间' },
  { key: 'metric:cpu', title: 'CPU' },
  { key: 'action', title: '操作' },
];

const defaults = resolveViewColumns(available, null);
assert.deepEqual(defaults.fieldKeys, ['instance_name', 'time', 'metric:cpu']);
assert.deepEqual(defaults.columns.map((column) => column.key), [
  'instance_name',
  'time',
  'metric:cpu',
  'action',
]);

const personalized = resolveViewColumns(available, [
  'metric:removed',
  'metric:cpu',
  'instance_name',
]);
assert.deepEqual(personalized.fieldKeys, ['metric:cpu', 'instance_name']);
assert.deepEqual(personalized.columns.map((column) => column.key), [
  'metric:cpu',
  'instance_name',
  'action',
]);

const stale = resolveViewColumns(available, ['metric:removed']);
assert.deepEqual(stale.fieldKeys, ['instance_name', 'time', 'metric:cpu']);
assert.equal(stale.columns.at(-1)?.key, 'action');
