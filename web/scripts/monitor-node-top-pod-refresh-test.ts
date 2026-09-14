import assert from 'node:assert/strict';

import {
  createNodeTopPodLoadCoordinator,
  shouldReloadNodeTopPods,
  type NodeTopPodLoadKey,
} from '../src/app/monitor/dashboards/objects/common/nodeTopPodLoad.ts';

function key(overrides: Partial<NodeTopPodLoadKey> = {}): NodeTopPodLoadKey {
  return {
    idValuesKey: 'node-a',
    interval: 15,
    timeKey: 'last_1h',
    isDashboardMode: true,
    loadTick: 1,
    ...overrides,
  };
}

const baseline = key();

assert.equal(
  shouldReloadNodeTopPods(null, baseline),
  true,
  '仪表盘模式且已选实例时应首次取数'
);

assert.equal(
  shouldReloadNodeTopPods(baseline, key()),
  false,
  '实例、时间窗、间隔与 loadTick 均不变时不应重载'
);

assert.equal(
  shouldReloadNodeTopPods(baseline, key({ loadTick: baseline.loadTick + 1 })),
  true,
  '同一实例与时间窗下仅 loadTick+1（刷新/自动刷新）必须重载'
);

assert.equal(
  shouldReloadNodeTopPods(baseline, key({ idValuesKey: 'node-b' })),
  true,
  '切换实例应重载'
);

assert.equal(
  shouldReloadNodeTopPods(baseline, key({ timeKey: 'last_6h' })),
  true,
  '切换时间窗应重载'
);

assert.equal(
  shouldReloadNodeTopPods(baseline, key({ isDashboardMode: false, loadTick: 99 })),
  false,
  '切出仪表盘模式必须停止取数'
);

assert.equal(
  shouldReloadNodeTopPods(null, key({ idValuesKey: '' })),
  false,
  '空实例不得发查询'
);

const coordinator = createNodeTopPodLoadCoordinator();
const staleGeneration = coordinator.begin();
const liveGeneration = coordinator.begin();

assert.equal(coordinator.shouldApply(staleGeneration), false, '迟到 generation 不得 apply');
assert.equal(coordinator.shouldApply(liveGeneration), true, '当前 generation 可以 apply');

const applied: string[] = [];
const race = createNodeTopPodLoadCoordinator();
const first = race.begin();
const second = race.begin();
if (race.shouldApply(first)) applied.push('stale');
if (race.shouldApply(second)) applied.push('live');
assert.deepEqual(applied, ['live'], '后发起的取数才能写入结果');

console.log('monitor-node-top-pod-refresh-test: ok');
