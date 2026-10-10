import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createIntl, createIntlCache } from 'react-intl';
import { describe, expect, it } from 'vitest';

import { flattenMessages } from '@/app/apm/__tests__/intl';
import rumEn from '@/app/rum/locales/en.json';
import rumZh from '@/app/rum/locales/zh.json';
import commonEn from '@/locales/en.json';
import commonZh from '@/locales/zh.json';

interface Nested {
  [key: string]: string | Nested;
}

const zh = {
  ...flattenMessages(commonZh as Nested),
  ...flattenMessages(rumZh as Nested),
};
const en = {
  ...flattenMessages(commonEn as Nested),
  ...flattenMessages(rumEn as Nested),
};

const missingKeys = [
  'rum.applications.loadFailed',
  'rum.compliance.statusFailed',
  'rum.export.label',
  'common.saved',
  'rum.errors.detail.stackCopied',
  'rum.sessions.viewSession',
  'rum.errors.detail.missingMapHint',
  'rum.errors.detail.copyStack',
  'rum.errors.detail.sampleHint',
  'rum.range.1h',
  'rum.range.24h',
  'rum.range.current',
  'rum.errors.detail.peakCount',
  'rum.errors.detail.times',
  'rum.errors.detail.attributes',
  'rum.filter.application',
  'rum.errors.type',
  'rum.errors.fingerprint',
  'common.copied',
  'rum.errors.copyFingerprint',
  'rum.releases.release',
  'rum.errors.filterTitle',
  'rum.traffic.label',
  'rum.errors.rowCount',
  'rum.funnels.convFromFirst',
  'rum.funnels.dropoff',
  'rum.funnels.list',
  'rum.funnels.stepUnit',
  'rum.sessions.healthy',
  'rum.sessions.hasReplayTag',
  'rum.sessions.actions',
  'rum.sessions.journeySteps',
  'rum.sessions.showAllEvents',
  'rum.sessions.clickToFilter',
  'rum.sessions.noEventsInRoute',
  'rum.cwv.good',
  'rum.cwv.needsImprove',
  'rum.cwv.poor',
  'rum.sessions.replayReady',
  'rum.sessions.replayNotAvailable',
  'rum.sessions.watchReplay',
  'rum.sessions.noReplayDesc',
  'rum.sessions.metadata',
  'rum.sessions.geo',
  'rum.sessions.device',
  'rum.sessions.browser',
  'rum.sessions.app',
  'rum.sessions.release',
  'rum.sessions.timeSpan',
  'rum.sessions.timeStart',
  'rum.sessions.timeEnd',
  'rum.sessions.quickFilter',
  'rum.sessions.detailTitle',
  'rum.sessions.loadFailed',
  'rum.views.dimensionTitle',
  'rum.views.aggregate',
  'rum.views.releaseDetail',
  'rum.views.routeDetail',
  'rum.views.sortByMetric',
  'rum.views.rowCount',
  'rum.views.searchPlaceholder',
];

function readSource(relativePath: string): string {
  return readFileSync(path.join(process.cwd(), relativePath), 'utf8');
}

describe('rum issue 5894 i18n', () => {
  it('补齐缺失 key，中英文成对且占位符一致', () => {
    for (const key of missingKeys) {
      expect(zh[key], key).toEqual(expect.any(String));
      expect(en[key], key).toEqual(expect.any(String));
      expect(zh[key].trim(), key).not.toBe('');
      expect(en[key].trim(), key).not.toBe('');
      expect(zh[key], key).not.toBe(key);
      expect(en[key], key).not.toBe(key);
      expect(zh[key], key).not.toBe(en[key]);
      const zhSlots = zh[key].match(/\{[a-zA-Z0-9_]+\}/g) || [];
      const enSlots = en[key].match(/\{[a-zA-Z0-9_]+\}/g) || [];
      expect(enSlots.sort(), key).toEqual(zhSlots.sort());
    }
  });

  it('会话时段硬编码改为 t()，且能格式化起止时间', () => {
    const source = readSource('src/app/rum/sessions/[sessionId]/page.tsx');
    expect(source).toContain("t('rum.sessions.timeStart'");
    expect(source).toContain("t('rum.sessions.timeEnd'");
    expect(source).not.toContain('始: {formatFullDateTime');
    expect(source).not.toContain('终: {formatFullDateTime');

    const intl = createIntl(
      {
        locale: 'zh',
        messages: {
          'rum.sessions.timeStart': zh['rum.sessions.timeStart'],
          'rum.sessions.timeEnd': zh['rum.sessions.timeEnd'],
        },
      },
      createIntlCache(),
    );
    expect(intl.formatMessage({ id: 'rum.sessions.timeStart' }, { time: '2026-01-01 00:00' })).toBe(
      '始: 2026-01-01 00:00',
    );
    expect(intl.formatMessage({ id: 'rum.sessions.timeEnd' }, { time: '2026-01-01 01:00' })).toBe(
      '终: 2026-01-01 01:00',
    );
  });

  it('回放加载错误不被页面直接展示，且不再含中文硬编码', () => {
    const replayData = readSource('src/app/rum/sessions/lib/replay-data.ts');
    const replayPage = readSource('src/app/rum/sessions/[sessionId]/replay/page.tsx');
    expect(replayData).not.toMatch(/[\u4e00-\u9fff]/);
    expect(replayPage).toContain('.catch(() => {');
    expect(replayPage).toContain('setEvents([])');
  });
});
