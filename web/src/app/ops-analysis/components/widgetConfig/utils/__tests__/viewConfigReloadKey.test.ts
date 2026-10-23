import assert from 'node:assert/strict';
import test from 'node:test';
import type { LayoutItem } from '../../../../types/dashBoard';
import { viewConfigReloadKey } from '../viewConfigReloadKey';

const item = (): LayoutItem => ({
  i: 'w1',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: '在线数',
  valueConfig: {
    chartType: 'single',
    dataSource: 3,
    descriptionField: 'note',
    singleStyle: { showIcon: true, iconKey: 'cc-host' },
    appearance: { frame: 'panel' },
  },
});

test('singleStyle and appearance do not change the data form reload key', () => {
  const current = item();
  const styled = item();
  styled.valueConfig = {
    ...styled.valueConfig,
    appearance: { frame: 'bare' },
    singleStyle: { showIcon: true, align: 'center' },
  };

  assert.equal(viewConfigReloadKey(current), viewConfigReloadKey(styled));
  assert.equal(viewConfigReloadKey(null), '');
});

test('data fields and widget identity still change the reload key', () => {
  const current = viewConfigReloadKey(item());
  const renamed = item();
  renamed.name = '离线数';
  const described = item();
  described.valueConfig = {
    ...described.valueConfig,
    descriptionField: 'host',
  };

  assert.notEqual(current, viewConfigReloadKey(renamed));
  assert.notEqual(current, viewConfigReloadKey(described));
});
