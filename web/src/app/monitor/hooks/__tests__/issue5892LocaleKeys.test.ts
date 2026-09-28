import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import monitorEn from '@/app/monitor/locales/en.json';
import monitorZh from '@/app/monitor/locales/zh.json';
import commonEn from '@/locales/en.json';
import commonZh from '@/locales/zh.json';

type Nested = { [key: string]: string | Nested };

const flatten = (nested: Nested, prefix = ''): Record<string, string> => {
  const messages: Record<string, string> = {};
  Object.entries(nested).forEach(([key, value]) => {
    const id = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      messages[id] = value;
      return;
    }
    Object.assign(messages, flatten(value, id));
  });
  return messages;
};

const zh = {
  ...flatten(commonZh as Nested),
  ...flatten(monitorZh as Nested),
};
const en = {
  ...flatten(commonEn as Nested),
  ...flatten(monitorEn as Nested),
};

const pairedKeys = [
  'monitor.events.count',
  'monitor.events.searchAssetName',
  'monitor.integrations.selectCloudRegion',
  'monitor.integrations.fetchingCloudRegions',
  'monitor.integrations.cloudRegionNoOptions',
  'monitor.integrations.fetchCloudRegions',
  'monitor.integrations.refreshCloudRegionsTip',
  'monitor.integrations.refreshStoredCloudRegionsTip',
  'monitor.integrations.aliyunRegionAuthFailed',
  'monitor.integrations.noTemplateColumns',
  'monitor.integrations.uploadExcel',
  'monitor.integrations.uploadExcelHint',
  'monitor.integrations.monitorInstance',
  'monitor.integrations.downloadTemplate',
  'monitor.integrations.formulaResultNamePlaceholder',
  'common.instance',
  'common.formatError',
];

describe('monitor issue 5892 missing keys', () => {
  it('中英文成对存在，且没有未替换的占位符', () => {
    pairedKeys.forEach((key) => {
      expect(zh[key], key).toEqual(expect.any(String));
      expect(en[key], key).toEqual(expect.any(String));
      expect(zh[key].trim(), key).not.toBe('');
      expect(en[key].trim(), key).not.toBe('');
      expect(zh[key], key).not.toBe(key);
      expect(en[key], key).not.toBe(key);
      const zhSlots = zh[key].match(/\{[a-zA-Z0-9_]+\}/g) || [];
      const enSlots = en[key].match(/\{[a-zA-Z0-9_]+\}/g) || [];
      expect(enSlots.sort(), key).toEqual(zhSlots.sort());
    });
  });

  it('已有同义文案的入口复用原 key', () => {
    const webRoot = resolve(__dirname, '../../../../..');
    const excelModal = readFileSync(
      resolve(webRoot, 'src/app/monitor/components/integration-contract/integration-excel-import-modal/index.tsx'),
      'utf8'
    );
    const formulaEditor = readFileSync(
      resolve(webRoot, 'src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx'),
      'utf8'
    );
    expect(excelModal).toContain("t('monitor.integrations.downloadTemplate')");
    expect(excelModal).not.toContain("t('common.downloadTemplate')");
    expect(formulaEditor).toContain("t('monitor.integrations.formulaResultNamePlaceholder')");
    expect(formulaEditor).not.toContain("t('monitor.events.formulaResultNamePlaceholder')");
    expect(zh['monitor.integrations.formulaResultNamePlaceholder']).toBe('请输入结果名称');
    expect(en['monitor.integrations.formulaResultNamePlaceholder']).toBe('Please enter a result name');
    expect(zh['monitor.integrations.downloadTemplate']).toBe('下载模板');
    expect(en['monitor.integrations.downloadTemplate']).toBe('Download Template');
  });
});
