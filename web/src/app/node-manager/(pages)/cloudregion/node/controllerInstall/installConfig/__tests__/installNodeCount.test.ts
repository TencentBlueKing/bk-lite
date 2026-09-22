// @vitest-environment node

import { describe, expect, it } from 'vitest';
import { countAccessAssets } from '../installNodeCount';
import en from '@/app/node-manager/locales/en.json';
import zh from '@/app/node-manager/locales/zh.json';

const columns = [
  { name: 'ip', required: true, is_only: true },
  { name: 'node_name', required: true },
  { name: 'organizations', required: true },
  { name: 'port', required: true },
  { name: 'username', required: true },
  { name: 'auth_type', required: true },
  { name: 'password', required: true }
];

const placeholder = {
  ip: null,
  node_name: null,
  organizations: ['default-org'],
  port: 22,
  username: 'root',
  auth_type: 'password',
  password: null
};

const filledNode = {
  key: 'node-1',
  ip: '10.0.0.8',
  node_name: '10.0.0.8',
  organizations: ['default-org'],
  port: 22,
  username: 'root',
  auth_type: 'password',
  password: 'secret'
};

describe('remote install node count', () => {
  it('explains the counting rule in both supported languages', () => {
    expect(zh['node-manager'].cloudregion.node.installInfo).toBe('安装信息');
    expect(zh['node-manager'].cloudregion.node.installNodeCount).toBe(
      '安装节点数：{count}'
    );
    expect(zh['node-manager'].cloudregion.node.installNodeCountHint).toBe(
      '仅统计必填信息完整的节点'
    );
    expect(en['node-manager'].cloudregion.node.installInfo).toBe(
      'Installation Information'
    );
    expect(en['node-manager'].cloudregion.node.installNodeCount).toContain(
      '{count}'
    );
    expect(en['node-manager'].cloudregion.node.installNodeCountHint).toContain(
      'complete required information'
    );
  });

  it('does not count the placeholder default row with empty IP, port 22 and username root', () => {
    expect(countAccessAssets([{ key: 'empty' }], columns, placeholder)).toBe(0);
    expect(
      countAccessAssets(
        [{ key: 'defaults', ...placeholder }],
        columns,
        placeholder
      )
    ).toBe(0);
  });

  it('counts a row only after its required fields are filled', () => {
    const partialNode = { ...filledNode, password: null };

    expect(countAccessAssets([partialNode], columns, placeholder)).toBe(0);
    expect(countAccessAssets([filledNode], columns, placeholder)).toBe(1);
  });

  it('updates after copying and deleting filled rows', () => {
    const copiedNode = { ...filledNode, key: 'node-copy' };
    const copiedRows = [filledNode, copiedNode];

    expect(countAccessAssets(copiedRows, columns, placeholder)).toBe(2);
    expect(countAccessAssets(copiedRows.slice(1), columns, placeholder)).toBe(1);
    expect(countAccessAssets([], columns, placeholder)).toBe(0);
  });

  it('counts valid batch imports while ignoring the retained placeholder', () => {
    const importedRows = [
      {
        ...filledNode,
        key: 'import-1',
        ip: '10.0.0.9',
        node_name: '10.0.0.9'
      },
      {
        ...filledNode,
        key: 'import-2',
        ip: '10.0.0.10',
        node_name: '10.0.0.10'
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
