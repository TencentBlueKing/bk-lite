import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { checkDataSourceAuth } from '../permissionChecker';

function ds(partial: Partial<DatasourceItem>): DatasourceItem {
  return partial as DatasourceItem;
}

describe('checkDataSourceAuth', () => {
  it('treats empty groups as globally visible only for builtin sources', () => {
    assert.equal(checkDataSourceAuth(ds({ is_build_in: true, groups: [] }), 10), true);
    assert.equal(
      checkDataSourceAuth(ds({ is_build_in: true, groups: undefined }), 10),
      true,
    );
  });

  it('denies custom sources with empty groups', () => {
    assert.equal(checkDataSourceAuth(ds({ is_build_in: false, groups: [] }), 10), false);
    assert.equal(checkDataSourceAuth(ds({ groups: [] }), 10), false);
    assert.equal(checkDataSourceAuth(ds({ is_build_in: false }), 10), false);
  });

  it('allows access when the user group is in the allowlist', () => {
    const source = ds({ is_build_in: false, groups: [10, 20] });
    assert.equal(checkDataSourceAuth(source, 10), true);
    assert.equal(checkDataSourceAuth(source, '20'), true);
    assert.equal(checkDataSourceAuth(source, 99), false);
    assert.equal(checkDataSourceAuth(source), false);
  });
});
