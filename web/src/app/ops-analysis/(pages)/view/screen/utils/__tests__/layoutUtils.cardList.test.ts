import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import type { WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import {
  addConfiguredScreenWidget,
  isScreenWidgetChartType,
} from '../layoutUtils';

const readLocale = (locale: 'zh' | 'en') =>
  JSON.parse(
    readFileSync(
      new URL(
        `../../../../../locales/${locale}.json`,
        import.meta.url,
      ),
      'utf8',
    ),
  );

const emptyViewSets: ScreenViewSets = {
  viewport: { width: 1920, height: 1080 },
  items: [],
  decorations: {},
};

const addWidget = (chartType: string) =>
  addConfiguredScreenWidget(emptyViewSets, {
    name: chartType,
    chartType,
  } as WidgetConfig);

test('screen accepts cardList with the shared 520x360 default', () => {
  assert.equal(isScreenWidgetChartType('cardList'), true);

  const created = addWidget('cardList');
  assert.equal(created.items.length, 1);
  assert.equal(created.items[0].chartType, 'cardList');
  assert.equal(created.items[0].valueConfig.chartType, 'cardList');
  assert.equal(created.items[0].w, 520);
  assert.equal(created.items[0].h, 360);
  assert.equal(created.items[0].valueConfig.appearance?.frame, 'panel');
});

test('screen locales include cardList widget copy', () => {
  for (const locale of ['zh', 'en'] as const) {
    const messages = readLocale(locale);
    assert.equal(typeof messages.opsAnalysis.screen.widgets.cardList, 'string');
    assert.equal(
      typeof messages.opsAnalysis.screen.widgetDescriptions.cardList,
      'string',
    );
    assert.equal(typeof messages.dataSource.cardList, 'string');
  }
});

test('screen still rejects unknown widget types with the original error', () => {
  assert.throws(
    () => addWidget('not-a-real-chart'),
    /Unsupported screen widget type: not-a-real-chart/,
  );
});
