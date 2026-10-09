// @vitest-environment node

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import en from '@/app/node-manager/locales/en.json';
import zh from '@/app/node-manager/locales/zh.json';

interface NestedMessages {
  [key: string]: string | NestedMessages;
}

function flattenMessages(nested: NestedMessages, prefix = ''): Record<string, string> {
  return Object.keys(nested).reduce<Record<string, string>>((messages, key) => {
    const value = nested[key];
    const messageKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      messages[messageKey] = value;
    } else {
      Object.assign(messages, flattenMessages(value, messageKey));
    }
    return messages;
  }, {});
}

const zhMessages = flattenMessages(zh as NestedMessages);
const enMessages = flattenMessages(en as NestedMessages);

const reusedKeys = [
  'node-manager.cloudregion.node.cpuArchitecture',
  'node-manager.cloudregion.Configuration.description',
  'node-manager.collector.executeFilePath',
  'node-manager.collector.executeParameters',
  'common.formatError'
];

function readSource(relativePath: string): string {
  return readFileSync(path.join(process.cwd(), relativePath), 'utf8');
}

describe('node-manager issue 4339 locale keys', () => {
  it('resolves reused labels in both languages', () => {
    for (const key of reusedKeys) {
      expect(zhMessages[key], key).toBeTruthy();
      expect(enMessages[key], key).toBeTruthy();
      expect(zhMessages[key]).not.toBe(enMessages[key]);
    }

    expect(zhMessages['common.formatError']).toBe('格式错误');
    expect(enMessages['common.formatError']).toBe('Invalid format');
    expect(zhMessages['node-manager.cloudregion.node.cpuArchitecture']).toBe('CPU架构');
    expect(enMessages['node-manager.cloudregion.node.cpuArchitecture']).toBe('CPU Architecture');
  });

  it('package modal and detail column no longer reference missing keys', () => {
    const modal = readSource(
      'src/app/node-manager/components/node-manager-collector-package-modal/index.tsx'
    );
    const columns = readSource('src/app/node-manager/hooks/index.tsx');
    const excelImport = readSource(
      'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installConfig/excelImportModal.tsx'
    );
    const tableRenderer = readSource(
      'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installConfig/tableRenderer.tsx'
    );

    expect(modal).toContain("t('node-manager.cloudregion.node.cpuArchitecture')");
    expect(modal).toContain("t('node-manager.cloudregion.Configuration.description')");
    expect(modal).toContain("t('node-manager.collector.executeFilePath')");
    expect(modal).toContain("t('node-manager.collector.executeParameters')");
    expect(modal).not.toContain('Configuration.cpuArchitecture');
    expect(modal).not.toContain("t('common.desc')");
    expect(modal).not.toContain('packetManage.executablePath');
    expect(modal).not.toContain('packetManage.executeParameters');

    expect(columns).toContain("t('node-manager.cloudregion.node.cpuArchitecture')");
    expect(columns).not.toContain("'CPU架构'");

    expect(excelImport).toContain("t('common.formatError')");
    expect(tableRenderer).toContain("t('common.formatError')");
  });
});
