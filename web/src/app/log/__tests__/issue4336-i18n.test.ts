import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createIntl, createIntlCache } from 'react-intl';
import { describe, expect, it } from 'vitest';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';

type NestedMessages = {
  [key: string]: string | NestedMessages;
};

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

const keys = [
  'log.analysis.unknownComponent',
  'log.analysis.comparedWithPrevious',
  'log.analysis.total',
  'common.searchPlaceHolder',
];

function readSource(relativePath: string): string {
  return readFileSync(path.join(process.cwd(), relativePath), 'utf8');
}

describe('log issue 4336 confirmed copy', () => {
  it('resolves the dashboard labels in both languages', () => {
    for (const key of keys) {
      expect(zhMessages[key], key).toBeTruthy();
      expect(enMessages[key], key).toBeTruthy();
      expect(zhMessages[key]).not.toBe(enMessages[key]);
    }
    expect(zhMessages['log.analysis.total']).toBe('总数');
    expect(enMessages['log.analysis.total']).toBe('Total');
    expect(zhMessages['common.searchPlaceHolder']).toBe('搜索...');
    expect(enMessages['common.searchPlaceHolder']).toBe('Search...');
  });

  it('formats the unknown component label with the chart type', () => {
    const intl = createIntl(
      { locale: 'en', messages: { 'log.analysis.unknownComponent': enMessages['log.analysis.unknownComponent'] } },
      createIntlCache()
    );
    expect(intl.formatMessage({ id: 'log.analysis.unknownComponent' }, { chartType: 'gauge' })).toBe(
      'Unknown component type: gauge'
    );
  });

  it('reads those labels through t() at the confirmed call sites', () => {
    const sources = [
      'src/app/log/(pages)/analysis/dashBoard/components/widgetWrapper.tsx',
      'src/app/log/(pages)/analysis/dashBoard/widgets/comKpiCard.tsx',
      'src/app/log/(pages)/analysis/dashBoard/widgets/docker/dockerDonutChart.tsx',
      'src/app/log/(pages)/analysis/page.tsx',
      'src/app/log/components/log-donut-chart/index.tsx',
      'src/app/log/components/log-kpi-card/index.tsx',
    ].map(readSource);

    expect(sources[0]).toContain("t('log.analysis.unknownComponent'");
    expect(sources[1]).toContain("t('log.analysis.comparedWithPrevious'");
    expect(sources[2]).toContain("t('log.analysis.total'");
    expect(sources[3]).toContain("t('common.searchPlaceHolder'");
    expect(sources[4]).toContain("t('log.analysis.total'");
    expect(sources[5]).toContain("t('log.analysis.comparedWithPrevious'");
    for (const source of sources) {
      expect(source).not.toContain('>较上一周期<');
      expect(source).not.toContain('>总数<');
      expect(source).not.toContain('placeholder="搜索..."');
    }
  });
});
