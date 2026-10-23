import assert from 'node:assert/strict';
import test from 'node:test';
import type { ScreenWidgetItem } from '../../../../../types/screen';
import { screenWidgetDataKey } from '../screenWidgetDataKey';

const item = (): ScreenWidgetItem => ({
  id: 'card-a',
  type: 'widget',
  chartType: 'single',
  title: '在线数',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  zIndex: 1,
  valueConfig: {
    chartType: 'single',
    dataSource: 3,
    descriptionField: 'note',
    singleStyle: { showIcon: true },
    appearance: { frame: 'panel' },
  },
});

test('singleStyle and appearance do not change the screen data key', () => {
  const current = item();
  const styled = item();
  styled.valueConfig = {
    ...styled.valueConfig,
    appearance: { frame: 'bare' },
    singleStyle: { showIcon: true, iconKey: 'cc-host', align: 'right' },
  };
  styled.x = 40;

  assert.equal(screenWidgetDataKey(current), screenWidgetDataKey(styled));
});

test('widget data and identity still change the screen data key', () => {
  const current = screenWidgetDataKey(item());
  const nextCard = item();
  nextCard.id = 'card-b';
  const described = item();
  described.valueConfig = {
    ...described.valueConfig,
    descriptionField: 'host',
  };

  assert.notEqual(current, screenWidgetDataKey(nextCard));
  assert.notEqual(current, screenWidgetDataKey(described));
});
