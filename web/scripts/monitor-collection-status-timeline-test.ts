import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { buildCollectionStatusTimeline } from '../src/app/monitor/dashboards/shared/utils/collection-status';

const SEGMENT_COUNT = 18;
const WINDOW_MS = 15 * 60 * 1000;
const START_MS = 1_700_000_000_000;
const END_MS = START_MS + WINDOW_MS;
const BUCKET_MS = WINDOW_MS / SEGMENT_COUNT;

const tones = (
  loadState: string | undefined,
  viewData: Array<{ time: number; value1?: number }>,
  sampleIntervalMs?: number
) =>
  buildCollectionStatusTimeline(
    loadState,
    viewData,
    START_MS,
    END_MS,
    SEGMENT_COUNT,
    sampleIntervalMs
  ).map((segment) => segment.tone);

const longGapTones = tones('success', [
  { time: START_MS, value1: 1 },
  { time: END_MS, value1: 1 }
]);

assert.equal(longGapTones.length, SEGMENT_COUNT);
assert.equal(longGapTones[0], 'success', 'window start success point may mark nearby buckets normal');
assert.equal(longGapTones[SEGMENT_COUNT - 1], 'success', 'window end success point may mark nearby buckets normal');
for (let index = 3; index < SEGMENT_COUNT - 3; index += 1) {
  assert.equal(
    longGapTones[index],
    'empty',
    `15m/18 buckets with only endpoints 900s apart must keep middle bucket ${index} empty, not paint the outage as success`
  );
}

const sampleEvery60s = Array.from({ length: Math.floor(WINDOW_MS / 60_000) + 1 }, (_, index) => ({
  time: START_MS + index * 60_000,
  value1: 1
}));
const continuousTones = tones('success', sampleEvery60s, 60_000);
assert.equal(continuousTones.length, SEGMENT_COUNT);
assert.deepEqual(
  continuousTones,
  Array.from({ length: SEGMENT_COUNT }, () => 'success'),
  '60s scrape against ~50s buckets must not insert periodic empty (false grey) buckets'
);

const queryErrorTones = tones('error', [
  { time: START_MS, value1: 1 },
  { time: END_MS, value1: 1 }
]);
assert.deepEqual(
  queryErrorTones,
  Array.from({ length: SEGMENT_COUNT }, () => 'error'),
  'loadState=error must keep the whole window as error'
);

const singlePointTones = tones('success', [{ time: START_MS + WINDOW_MS / 2, value1: 1 }]);
assert.ok(
  singlePointTones.some((tone) => tone === 'success'),
  'a single success point must cover nearby buckets'
);
assert.ok(
  singlePointTones.some((tone) => tone === 'empty'),
  'a single success point must not paint the entire window success'
);
const singleCoverageBuckets = singlePointTones.filter((tone) => tone === 'success').length;
assert.ok(
  singleCoverageBuckets <= Math.ceil((BUCKET_MS * 3) / BUCKET_MS),
  'a single success point must only cover nearby buckets'
);

const callerFiles = [
  'src/app/monitor/dashboards/objects/common/simple-dashboard-core.tsx',
  'src/app/monitor/dashboards/objects/mysql/dashboard.tsx',
  'src/app/monitor/dashboards/objects/mongodb/dashboard.tsx',
  'src/app/monitor/dashboards/objects/k8s-cluster/dashboard.tsx',
  'src/app/monitor/dashboards/objects/k3s-cluster/dashboard.tsx'
];

for (const callerFile of callerFiles) {
  const source = readFileSync(resolve(process.cwd(), callerFile), 'utf8');
  assert.match(
    source,
    /buildCollectionStatusTimeline\([\s\S]*?currentInstanceInterval\s*\*\s*1000/,
    `${callerFile} must pass currentInstanceInterval*1000 into buildCollectionStatusTimeline`
  );
}

console.log('monitor collection status timeline tests passed');
