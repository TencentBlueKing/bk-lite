import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import type { WarningItem } from '../src/app/ops-analysis/api/importExport';
import {
  buildSecretSupplements,
  getSecretSupplementKey,
  getVisibleImportWarnings,
  hasBlockingImportWarnings,
  STRING_LIST_MIGRATION_WARNING_CODE,
} from '../src/app/ops-analysis/components/importExport/secretSupplements';

const newDatasourceWarning: WarningItem = {
  code: 'OA_SECRET_PLACEHOLDER',
  message: 'missing API key',
  object_key: 'new-source::',
  field: 'connection_config.headers.X-API-Key',
};
const conflictWarning: WarningItem = {
  code: 'OA_SECRET_PLACEHOLDER',
  message: 'missing authorization',
  object_key: 'existing-source::',
  field: 'connection_config.headers.Authorization',
};
const warnings = [newDatasourceWarning, conflictWarning];
const newDatasourceKey = getSecretSupplementKey(newDatasourceWarning)!;
const conflictKey = getSecretSupplementKey(conflictWarning)!;

assert.equal(hasBlockingImportWarnings(warnings, {}, {}), true);
assert.equal(hasBlockingImportWarnings([newDatasourceWarning], {}, {
  [newDatasourceKey]: '   ',
}), true);
assert.equal(hasBlockingImportWarnings([newDatasourceWarning], {}, {
  [newDatasourceKey]: '******',
}), true);
assert.equal(hasBlockingImportWarnings(warnings, {
  'existing-source::': 'overwrite',
}, {
  [newDatasourceKey]: 'new-api-key',
}), false);
assert.equal(hasBlockingImportWarnings(warnings, {
  'existing-source::': 'rename',
}, {
  [newDatasourceKey]: 'new-api-key',
}), true);
assert.equal(hasBlockingImportWarnings(warnings, {
  'existing-source::': 'rename',
}, {
  [newDatasourceKey]: 'new-api-key',
  [conflictKey]: 'renamed-source-token',
}), false);

assert.deepEqual(getVisibleImportWarnings(warnings, {
  'existing-source::': 'skip',
}), [newDatasourceWarning]);
assert.deepEqual(buildSecretSupplements(warnings, {
  'existing-source::': 'skip',
}, {
  [newDatasourceKey]: 'new-api-key',
  [conflictKey]: 'must-not-be-submitted',
}), [{
  object_key: 'new-source::',
  field: 'connection_config.headers.X-API-Key',
  value: 'new-api-key',
}]);
assert.deepEqual(buildSecretSupplements(warnings, {
  'existing-source::': 'overwrite',
}, {
  [newDatasourceKey]: 'new-api-key',
  [conflictKey]: 'replacement-token',
}), [
  {
    object_key: 'new-source::',
    field: 'connection_config.headers.X-API-Key',
    value: 'new-api-key',
  },
  {
    object_key: 'existing-source::',
    field: 'connection_config.headers.Authorization',
    value: 'replacement-token',
  },
]);
assert.deepEqual(buildSecretSupplements([newDatasourceWarning], {}, {
  [newDatasourceKey]: '  whitespace-sensitive-api-key  ',
}), [{
  object_key: 'new-source::',
  field: 'connection_config.headers.X-API-Key',
  value: '  whitespace-sensitive-api-key  ',
}]);
assert.deepEqual(buildSecretSupplements([newDatasourceWarning], {}, {
  [newDatasourceKey]: ' ****** ',
}), [{
  object_key: 'new-source::',
  field: 'connection_config.headers.X-API-Key',
  value: ' ****** ',
}]);
assert.deepEqual(buildSecretSupplements([newDatasourceWarning], {}, {
  [newDatasourceKey]: '******',
}), []);

const migrationWarning: WarningItem = {
  code: STRING_LIST_MIGRATION_WARNING_CODE,
  message: '旧 stringList 将规范为 string + multiple',
  object_key: 'dashboard::host',
  field: 'filters.instance_ids__stringList',
};
const migrationDatasourceWarnings: WarningItem[] = [
  {
    code: STRING_LIST_MIGRATION_WARNING_CODE,
    message: '数据源 params 使用旧类型 stringList',
    object_key: 'host-a::api',
    field: 'params.instance_ids',
  },
  {
    code: STRING_LIST_MIGRATION_WARNING_CODE,
    message: '数据源 params 使用旧类型 stringList',
    object_key: 'host-b::api',
    field: 'params.instance_ids',
  },
  {
    code: STRING_LIST_MIGRATION_WARNING_CODE,
    message: '数据源 params 使用旧类型 stringList',
    object_key: 'host-c::api',
    field: 'params.instance_ids',
  },
  {
    code: STRING_LIST_MIGRATION_WARNING_CODE,
    message: '数据源 params 使用旧类型 stringList',
    object_key: 'host-d::api',
    field: 'params.instance_ids',
  },
  migrationWarning,
];

assert.deepEqual(
  getVisibleImportWarnings([migrationWarning], {}),
  [migrationWarning],
  'OA_STRING_LIST_MIGRATION 仍应展示',
);
assert.equal(
  hasBlockingImportWarnings([migrationWarning], {}, {}),
  false,
  '仅 migration warning 不得阻断导入',
);

const allOverwriteDecisions = {
  'host-a::api': 'overwrite' as const,
  'host-b::api': 'overwrite' as const,
  'host-c::api': 'overwrite' as const,
  'host-d::api': 'overwrite' as const,
};
assert.equal(
  hasBlockingImportWarnings(migrationDatasourceWarnings, allOverwriteDecisions, {}),
  false,
  'migration warning + 4 个冲突全部覆盖后不得阻断',
);

assert.equal(
  hasBlockingImportWarnings(
    [migrationWarning, newDatasourceWarning],
    {},
    {},
  ),
  true,
  'migration + 未补全 Secret 仍应阻断',
);

assert.equal(
  hasBlockingImportWarnings(
    [migrationWarning, newDatasourceWarning],
    {},
    { [newDatasourceKey]: 'filled-secret' },
  ),
  false,
  'migration + Secret 已补全应可导入',
);

assert.equal(
  hasBlockingImportWarnings(
    [migrationWarning, conflictWarning],
    { 'existing-source::': 'overwrite' },
    {},
  ),
  false,
  'migration + Secret overwrite 豁免应可导入',
);

assert.equal(
  hasBlockingImportWarnings(
    [{
      code: 'OA_UNKNOWN_FUTURE_WARNING',
      message: '未知 warning 默认阻断',
      object_key: 'any::key',
      field: 'any.field',
    }],
    { 'any::key': 'overwrite' },
    {},
  ),
  true,
  '未知 warning code 必须继续阻断',
);

const modalSource = readFileSync(
  new URL('../src/app/ops-analysis/components/importExport/importModal.tsx', import.meta.url),
  'utf8',
);
assert.match(modalSource, /<Input\.Password/);
assert.match(modalSource, /secret_supplements:\s*buildSecretSupplements/);
assert.match(modalSource, /disabled=\{hasBlockingWarnings\}/);
assert.match(
  modalSource,
  /hasBlockingImportWarnings/,
  '生产 importModal 必须使用 hasBlockingImportWarnings',
);

console.log('ops analysis import secret supplements tests passed');
