import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const chartSource = readFileSync(
  join(
    root,
    'src/app/log/(pages)/analysis/dashBoard/widgets/docker/dockerDonutChart.tsx'
  ),
  'utf8'
);

const emptyEffectWithObserver = /useEffect\(\(\)\s*=>\s*\{[\s\S]*?\},\s*\[\s*\]\s*\)/g;
const bindsObserverInEmptyEffect = [...chartSource.matchAll(emptyEffectWithObserver)].some(
  (match) => /new ResizeObserver/.test(match[0]) || /\.observe\(/.test(match[0])
);

assert.equal(
  bindsObserverInEmptyEffect,
  false,
  'DockerDonutChart must not bind ResizeObserver inside useEffect with empty deps'
);
assert.match(
  chartSource,
  /useCallback\(\s*\(node:\s*HTMLDivElement\s*\|\s*null\)/,
  'DockerDonutChart must bind size observation with a callback ref'
);
assert.match(
  chartSource,
  /ref=\{containerCallbackRef\}/,
  'sized container must use the callback ref so empty→data remounts rebind'
);
assert.match(
  chartSource,
  /from ['"]\.\/dockerDonutSizeObserver['"]/,
  'chart must reuse the extracted size binder'
);
assert.match(
  chartSource,
  /if\s*\(\s*!chartOption\s*\)\s*\{\s*return\s*<ChartEmptyState/,
  'empty state must not render the sized container'
);
assert.match(
  chartSource,
  /size\.w\s*>\s*0\s*&&/,
  'center total must stay gated on size.w > 0'
);
assert.match(chartSource, /总数/, 'center copy must remain 总数');

class FakeResizeObserver {
  observeCalls: unknown[] = [];
  disconnectCalls = 0;

  constructor(public readonly callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.observeCalls.push(target);
  }

  disconnect() {
    this.disconnectCalls += 1;
  }

  unobserve() {}
}

const created: FakeResizeObserver[] = [];
const FakeObserver = class extends FakeResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    super(callback);
    created.push(this);
  }
} as unknown as typeof ResizeObserver;

async function main() {
  const sizes: Array<{ w: number; h: number }> = [];
  const observerModule = await import(
    '../src/app/log/(pages)/analysis/dashBoard/widgets/docker/dockerDonutSizeObserver.ts'
  );
  const binder = observerModule.createDockerDonutSizeBinder(
    (size: { w: number; h: number }) => sizes.push(size),
    FakeObserver
  );

  binder.bind(null);
  assert.equal(created.length, 0, 'empty node must not construct or observe');

  const firstNode = { id: 'first' } as unknown as Element;
  binder.bind(firstNode);
  assert.equal(created.length, 1, 'non-empty node must observe current DOM');
  assert.equal(created[0].observeCalls[0], firstNode);
  assert.equal(created[0].disconnectCalls, 0);

  const secondNode = { id: 'second' } as unknown as Element;
  binder.bind(secondNode);
  assert.equal(created[0].disconnectCalls, 1, 'rebinding must disconnect the previous observer');
  assert.equal(created.length, 2, 'rebinding must observe the new node');
  assert.equal(created[1].observeCalls[0], secondNode);

  binder.bind(null);
  assert.equal(created[1].disconnectCalls, 1, 'returning to empty must disconnect');
  assert.equal(created.length, 2, 'empty rebind must not observe a missing container');

  binder.unbind();
  assert.equal(created[1].disconnectCalls, 1, 'unbind after empty bind stays disconnected');

  console.log('log docker donut resize behavior OK');
}

void main();
