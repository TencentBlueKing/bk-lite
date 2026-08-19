// @vitest-environment node

import { describe, expect, it } from 'vitest';
import { countAccessAssets } from '../automaticAssetCount';

const columns = [
  { name: 'node_ids', required: true },
  { name: 'host', required: true },
  { name: 'port', required: true },
  { name: 'instance_name', required: true, is_only: true },
  { name: 'group_ids' }
];

const placeholder = {
  node_ids: null,
  host: null,
  port: 5432,
  instance_name: null,
  group_ids: ['default-group']
};

const filledAsset = {
  key: 'asset-1',
  node_ids: ['node-1'],
  host: 'db.internal',
  port: 5432,
  instance_name: 'db.internal:5432',
  group_ids: ['default-group']
};

describe('automatic integration access asset count', () => {
  it('does not count an empty placeholder or a row with defaults only', () => {
    expect(countAccessAssets([{ key: 'empty' }], columns, placeholder)).toBe(0);
    expect(
      countAccessAssets(
        [{ key: 'defaults', ...placeholder }],
        columns,
        placeholder
      )
    ).toBe(0);
  });

  it('counts a row only after its required and unique asset fields are filled', () => {
    const partialAsset = { ...filledAsset, node_ids: [] };

    expect(countAccessAssets([partialAsset], columns, placeholder)).toBe(0);
    expect(countAccessAssets([filledAsset], columns, placeholder)).toBe(1);
  });

  it('updates after copying and deleting filled rows', () => {
    const copiedAsset = { ...filledAsset, key: 'asset-copy' };
    const copiedRows = [filledAsset, copiedAsset];

    expect(countAccessAssets(copiedRows, columns, placeholder)).toBe(2);
    expect(countAccessAssets(copiedRows.slice(1), columns, placeholder)).toBe(1);
    expect(countAccessAssets([], columns, placeholder)).toBe(0);
  });

  it('counts valid batch imports while ignoring the retained placeholder', () => {
    const importedRows = [
      {
        ...filledAsset,
        key: 'import-1',
        host: 'db-1.internal',
        instance_name: 'db-1.internal:5432'
      },
      {
        ...filledAsset,
        key: 'import-2',
        host: 'db-2.internal',
        instance_name: 'db-2.internal:5432'
      }
    ];

    expect(
      countAccessAssets(
        [{ key: 'placeholder', ...placeholder }, ...importedRows],
        columns,
        placeholder
      )
    ).toBe(2);
  });
});
