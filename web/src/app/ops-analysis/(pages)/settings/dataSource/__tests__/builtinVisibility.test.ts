import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  buildBuiltinGroupsPayload,
  canEditBuiltinDatasourceGroups,
  isBuiltinDatasource,
  isDatasourceDefinitionReadOnly,
} from '../operateModalUtils';

describe('isBuiltinDatasource', () => {
  it('returns false when the row is missing or not builtin', () => {
    assert.equal(isBuiltinDatasource(), false);
    assert.equal(isBuiltinDatasource({}), false);
    assert.equal(isBuiltinDatasource({ is_build_in: false }), false);
  });

  it('returns true only when is_build_in is true', () => {
    assert.equal(isBuiltinDatasource({ is_build_in: true }), true);
  });
});

describe('isDatasourceDefinitionReadOnly', () => {
  it('locks definition fields in view mode for custom sources', () => {
    assert.equal(isDatasourceDefinitionReadOnly('view', { is_build_in: false }), true);
  });

  it('locks definition fields for builtin sources even in edit mode', () => {
    assert.equal(isDatasourceDefinitionReadOnly('edit', { is_build_in: true }), true);
    assert.equal(isDatasourceDefinitionReadOnly('view', { is_build_in: true }), true);
  });

  it('allows definition edits for custom add and edit', () => {
    assert.equal(isDatasourceDefinitionReadOnly('add'), false);
    assert.equal(isDatasourceDefinitionReadOnly('edit', { is_build_in: false }), false);
  });
});

describe('canEditBuiltinDatasourceGroups', () => {
  it('allows only superusers to edit builtin organization lists', () => {
    assert.equal(canEditBuiltinDatasourceGroups(true, { is_build_in: true }), true);
    assert.equal(canEditBuiltinDatasourceGroups(false, { is_build_in: true }), false);
    assert.equal(canEditBuiltinDatasourceGroups(true, { is_build_in: false }), false);
    assert.equal(canEditBuiltinDatasourceGroups(true), false);
  });
});

describe('buildBuiltinGroupsPayload', () => {
  it('keeps positive integer group ids', () => {
    assert.deepEqual(buildBuiltinGroupsPayload([1, 2, 3]), { groups: [1, 2, 3] });
  });

  it('filters invalid ids and non-array input, including empty lists', () => {
    assert.deepEqual(buildBuiltinGroupsPayload([]), { groups: [] });
    assert.deepEqual(buildBuiltinGroupsPayload([1, 0, -2, 1.5, '3', null]), { groups: [1] });
    assert.deepEqual(buildBuiltinGroupsPayload(undefined), { groups: [] });
  });
});
