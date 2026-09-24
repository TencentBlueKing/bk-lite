import assert from 'node:assert/strict';
import test from 'node:test';
import { buildRoleFieldOptions, dropRoleValueMissingFrom } from '../chartFieldOptions';

test('value field options include string schema fields and preview keys', () => {
  const options = buildRoleFieldOptions(
    [
      { key: 'source_ip', title: '上报IP', value_type: 'string' },
      { key: 'message', title: '日志内容', value_type: 'string' },
    ],
    [
      { value: '208036', name: '10.51.176.171' },
    ],
  );

  assert.deepEqual(
    options.map((option) => option.value),
    ['source_ip', 'message', 'value', 'name'],
  );
  assert.equal(options[0]?.label, 'source_ip (上报IP)');
});

test('field options keep string-typed counts and ignore multi-series names', () => {
  const options = buildRoleFieldOptions(
    [{ key: 'value', title: '次数', value_type: 'string' }],
    {
      cpu: [{ name: '10:00', value: 1 }],
      mem: [{ name: '10:00', value: 2 }],
    },
  );

  assert.deepEqual(
    options.map((option) => option.value),
    ['value', 'name'],
  );
});

test('tuple samples add no column names', () => {
  const options = buildRoleFieldOptions([], [[1710000000, 12]]);
  assert.deepEqual(options, []);
});

test('a saved column stays until the new sample and schema both lack it', () => {
  const allowed = new Set(
    buildRoleFieldOptions(
      [{ key: 'value', title: '次数', value_type: 'string' }],
      [{ host: 'web' }],
    ).map((option) => option.value),
  );

  assert.equal(dropRoleValueMissingFrom('value', allowed), 'value');
  assert.equal(dropRoleValueMissingFrom('src_ip', allowed), undefined);
});
