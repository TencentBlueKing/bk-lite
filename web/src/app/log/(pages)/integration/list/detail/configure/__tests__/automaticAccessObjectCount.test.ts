// @vitest-environment node

import { describe, expect, it } from 'vitest';
import { countAccessAssets } from '../automaticAccessObjectCount';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';

const columns = [
  { name: 'node_ids', required: true },
  { name: 'instance_name', required: true },
  { name: 'group_ids', required: true }
];

const placeholder = {
  node_ids: null,
  instance_name: null,
  group_ids: ['default-group']
};

const filledObject = {
  instance_id: 'object-1',
  node_ids: ['node-1'],
  instance_name: 'nginx-prod',
  group_ids: ['default-group']
};

describe('automatic log integration access object count', () => {
  it('renames the table title and explains the counting rule in both languages', () => {
    expect(zh.log.integration.MonitoredObject).toBe('接入对象');
    expect(zh.log.integration.accessObjectCount).toBe('接入对象数：{count}');
    expect(zh.log.integration.accessObjectCountHint).toBe(
      '仅统计必填信息完整的对象'
    );
    expect(en.log.integration.MonitoredObject).toBe('Access Object');
    expect(en.log.integration.accessObjectCount).toContain('{count}');
    expect(en.log.integration.accessObjectCountHint).toContain(
      'complete required information'
    );
  });

  it('does not count an empty placeholder or a row with defaults only', () => {
    expect(countAccessAssets([{ instance_id: 'empty' }], columns, placeholder)).toBe(
      0
    );
    expect(
      countAccessAssets(
        [{ instance_id: 'defaults', ...placeholder }],
        columns,
        placeholder
      )
    ).toBe(0);
  });

  it('counts a row only after its required fields are filled', () => {
    const partialObject = { ...filledObject, node_ids: [] };

    expect(countAccessAssets([partialObject], columns, placeholder)).toBe(0);
    expect(countAccessAssets([filledObject], columns, placeholder)).toBe(1);
  });

  it('updates after copying and deleting filled rows', () => {
    const copiedObject = { ...filledObject, instance_id: 'object-copy' };
    const copiedRows = [filledObject, copiedObject];

    expect(countAccessAssets(copiedRows, columns, placeholder)).toBe(2);
    expect(countAccessAssets(copiedRows.slice(1), columns, placeholder)).toBe(1);
    expect(countAccessAssets([], columns, placeholder)).toBe(0);
  });

  it('counts valid batch imports while ignoring the retained placeholder', () => {
    const importedRows = [
      {
        ...filledObject,
        instance_id: 'import-1',
        instance_name: 'nginx-1'
      },
      {
        ...filledObject,
        instance_id: 'import-2',
        instance_name: 'nginx-2'
      }
    ];

    expect(
      countAccessAssets(
        [{ instance_id: 'placeholder', ...placeholder }, ...importedRows],
        columns,
        placeholder
      )
    ).toBe(2);
  });
});
