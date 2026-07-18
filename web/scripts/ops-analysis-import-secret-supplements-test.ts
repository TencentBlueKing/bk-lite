import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import type { WarningItem } from '../src/app/ops-analysis/api/importExport';
import {
  buildSecretSupplements,
  getSecretSupplementKey,
  getVisibleImportWarnings,
  hasBlockingImportWarnings,
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

const modalSource = readFileSync(
  new URL('../src/app/ops-analysis/components/importExport/importModal.tsx', import.meta.url),
  'utf8',
);
assert.match(modalSource, /<Input\.Password/);
assert.match(modalSource, /secret_supplements:\s*buildSecretSupplements/);
assert.match(modalSource, /disabled=\{hasBlockingWarnings\}/);

console.log('ops analysis import secret supplements tests passed');
