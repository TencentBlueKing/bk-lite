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

test('screen accepts eventTimeline and radar the same way dashboard already does', () => {
  assert.equal(isScreenWidgetChartType('eventTimeline'), true);
  assert.equal(isScreenWidgetChartType('radar'), true);

  const timeline = addWidget('eventTimeline');
  assert.equal(timeline.items.length, 1);
  assert.equal(timeline.items[0].chartType, 'eventTimeline');
  assert.equal(timeline.items[0].valueConfig.chartType, 'eventTimeline');

  const radar = addWidget('radar');
  assert.equal(radar.items.length, 1);
  assert.equal(radar.items[0].chartType, 'radar');
  assert.equal(radar.items[0].valueConfig.chartType, 'radar');

  assert.equal(timeline.items[0].w, 520);
  assert.equal(timeline.items[0].h, 360);
  assert.equal(radar.items[0].w, 360);
  assert.equal(radar.items[0].h, 300);
});

test('screen locales include eventTimeline and radar widget copy', () => {
  for (const locale of ['zh', 'en'] as const) {
    const messages = readLocale(locale);
    assert.equal(
      typeof messages.opsAnalysis.screen.widgets.eventTimeline,
      'string',
    );
    assert.equal(typeof messages.opsAnalysis.screen.widgets.radar, 'string');
    assert.equal(
      typeof messages.opsAnalysis.screen.widgetDescriptions.eventTimeline,
      'string',
    );
    assert.equal(
      typeof messages.opsAnalysis.screen.widgetDescriptions.radar,
      'string',
    );
  }
});

test('screen still rejects unknown widget types with the original error', () => {
  assert.throws(
    () => addWidget('not-a-real-chart'),
    /Unsupported screen widget type: not-a-real-chart/,
  );
});
