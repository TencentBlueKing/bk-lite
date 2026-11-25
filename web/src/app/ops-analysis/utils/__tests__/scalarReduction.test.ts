import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readScalarCalc,
  reduceScalarRecords,
  scalarCalcFromForm,
  singleValueSourceReady,
} from '../scalarReduction';

const hosts = [
  { host: 'a', cpu: 10, time: '2026-01-01T00:02:00Z' },
  { host: 'b', cpu: null, time: '2026-01-01T00:03:00Z' },
  { host: 'c', cpu: '30', time: '2026-01-01T00:01:00Z' },
  { host: 'd', cpu: '高', time: '2026-01-01T00:04:00Z' },
];

test('count uses records and ignores the envelope count', () => {
  assert.deepEqual(reduceScalarRecords([], { method: 'count' }), { status: 'value', value: 0 });
  assert.deepEqual(reduceScalarRecords({ items: [] }, { method: 'count' }), { status: 'value', value: 0 });
  assert.deepEqual(
    reduceScalarRecords({ count: 100, items: [{ value: 2 }, { value: 4 }] }, { method: 'count' }),
    { status: 'value', value: 2 },
  );
  assert.deepEqual(reduceScalarRecords({ value: 37.5, unit: '%' }, { method: 'count' }), {
    status: 'value',
    value: 1,
  });
  assert.deepEqual(reduceScalarRecords([18, 0, 6], { method: 'count' }), { status: 'value', value: 3 });
});

test('numeric reductions skip values that cannot be converted', () => {
  assert.deepEqual(reduceScalarRecords(hosts, { method: 'avg', field: 'cpu' }), { status: 'value', value: 20 });
  assert.deepEqual(reduceScalarRecords(hosts, { method: 'max', field: 'cpu' }), { status: 'value', value: 30 });
  assert.deepEqual(reduceScalarRecords(hosts, { method: 'min', field: 'cpu' }), { status: 'value', value: 10 });
  assert.deepEqual(reduceScalarRecords(hosts, { method: 'sum', field: 'cpu' }), { status: 'value', value: 40 });
  assert.deepEqual(reduceScalarRecords([18, 0, 6], { method: 'avg' }), { status: 'value', value: 8 });
  assert.deepEqual(reduceScalarRecords([18, '0.00', '6'], { method: 'sum' }), { status: 'value', value: 24 });
});

test('empty rows and non-numeric rows use different results', () => {
  assert.deepEqual(reduceScalarRecords([], { method: 'avg', field: 'cpu' }), { status: 'empty' });
  assert.deepEqual(reduceScalarRecords({}, { method: 'max' }), { status: 'empty' });
  assert.deepEqual(
    reduceScalarRecords([{ cpu: null }, { cpu: '高' }], { method: 'avg', field: 'cpu' }),
    { status: 'uncomputable' },
  );
  assert.deepEqual(reduceScalarRecords([18, 0, 6], { method: 'avg', field: 'cpu' }), {
    status: 'uncomputable',
  });
});

test('latest follows the time field and keeps the later row on a tie', () => {
  assert.deepEqual(
    reduceScalarRecords(hosts, { method: 'latest', field: 'cpu', timeField: 'time' }),
    { status: 'value', value: 10 },
  );
  assert.deepEqual(
    reduceScalarRecords(
      [
        { cpu: 1, time: '2026-01-01T00:00:00Z' },
        { cpu: 40, time: '2026-01-01T00:04:00Z' },
      ],
      { method: 'latest', field: 'cpu', timeField: 'time' },
    ),
    { status: 'value', value: 40 },
  );
  assert.deepEqual(
    reduceScalarRecords(
      [
        { cpu: 1, time: 10 },
        { cpu: 2, time: 10 },
      ],
      { method: 'latest', field: 'cpu', timeField: 'time' },
    ),
    { status: 'value', value: 2 },
  );
  assert.deepEqual(
    reduceScalarRecords([18, 0, 6], { method: 'latest' }),
    { status: 'uncomputable' },
  );
});

test('a list envelope stays one record', () => {
  assert.deepEqual(
    reduceScalarRecords({ list: [{ cpu: 1 }, { cpu: 2 }] }, { method: 'count' }),
    { status: 'value', value: 1 },
  );
});

test('form and source readiness ignore a missing calculation', () => {
  assert.equal(scalarCalcFromForm({ method: undefined }), undefined);
  assert.deepEqual(
    scalarCalcFromForm({ method: 'latest', field: ' cpu ', timeField: ' time ' }),
    { method: 'latest', field: 'cpu', timeField: 'time' },
  );
  assert.deepEqual(scalarCalcFromForm({ method: 'count', field: 'cpu' }), { method: 'count' });
  assert.equal(readScalarCalc({ method: 'mean' }), undefined);
  assert.equal(singleValueSourceReady({ dataSource: 1, selectedFields: [] }), false);
  assert.equal(
    singleValueSourceReady({ dataSource: 1, selectedFields: [], scalarCalc: { method: 'count' } }),
    true,
  );
  assert.equal(
    singleValueSourceReady({ dataSource: 1, selectedFields: ['cpu'] }),
    true,
  );
});
