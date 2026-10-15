import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createDelayedClickScheduler,
  createRightClickGesture,
  nearestRadarIndicatorIndex,
  openPreparedInteractionNavigation,
  pieSectorSelectedMode,
  readRadarClickGeometry,
} from '@/app/ops-analysis/utils/interactionBehavior';

test('line click waits and cancels on dblclick or data zoom', () => {
  const pending: Array<{ callback: () => void; ms: number } | null> = [];
  const scheduler = createDelayedClickScheduler(250, {
    set: (callback, ms) => {
      pending.push({ callback, ms });
      return pending.length;
    },
    clear: (id) => {
      pending[id - 1] = null;
    },
  });
  let opened = 0;
  scheduler.schedule(() => {
    opened += 1;
  });
  assert.equal(pending[0]?.ms, 250);
  pending[0]?.callback();
  assert.equal(opened, 1);

  scheduler.schedule(() => {
    opened += 1;
  });
  scheduler.cancel();
  assert.equal(pending[1], null);
  scheduler.schedule(() => {
    opened += 1;
  });
  assert.equal(opened, 1);
  pending[2]?.callback();
  scheduler.schedule(() => {
    opened += 1;
  });
  pending[3]?.callback();
  assert.equal(opened, 2);
});

test('dispose only clears the pending click timer', () => {
  const pending: Array<{ callback: () => void; ms: number } | null> = [];
  const scheduler = createDelayedClickScheduler(250, {
    set: (callback, ms) => {
      pending.push({ callback, ms });
      return pending.length;
    },
    clear: (id) => {
      pending[id - 1] = null;
    },
  });
  let opened = 0;
  scheduler.schedule(() => {
    opened += 1;
  });
  scheduler.dispose();
  assert.equal(pending.length, 1);
  assert.equal(pending[0], null);
  assert.equal(opened, 0);
});

test('right click opens only for a short move that hits an object', () => {
  const gesture = createRightClickGesture(6);
  gesture.pointerDown({ button: 2, clientX: 10, clientY: 20 });
  const click = gesture.decide({ clientX: 12, clientY: 21 }, true);
  assert.equal(click.open, true);
  assert.equal(click.stopImmediatePropagation, true);

  gesture.pointerDown({ button: 2, clientX: 10, clientY: 20 });
  const drag = gesture.decide({ clientX: 16, clientY: 20 }, true);
  assert.equal(drag.open, false);
  assert.equal(drag.dragged, true);
  assert.equal(drag.stopImmediatePropagation, false);

  gesture.pointerDown({ button: 2, clientX: 10, clientY: 20 });
  assert.equal(gesture.decide({ clientX: 10, clientY: 20 }, false).open, false);
  assert.equal(gesture.decide({ clientX: 10, clientY: 20 }, true).open, false);
  gesture.pointerDown({ button: 0, clientX: 1, clientY: 1 });
  assert.equal(gesture.decide({ clientX: 1, clientY: 1 }, true).open, false);
});

test('radar nearest indicator uses the hit position when dim index is absent', () => {
  const center = { x: 100, y: 100 };
  assert.equal(nearestRadarIndicatorIndex({ x: 100, y: 40 }, center, 4), 0);
  assert.equal(nearestRadarIndicatorIndex({ x: 40, y: 100 }, center, 4), 1);
  assert.equal(nearestRadarIndicatorIndex({ x: 100, y: 160 }, center, 4), 2);
  assert.equal(nearestRadarIndicatorIndex({ x: 160, y: 100 }, center, 4), 3);
  assert.deepEqual(readRadarClickGeometry({
    getWidth: () => 200,
    getHeight: () => 100,
    getModel: () => ({
      getComponent: () => ({ coordinateSystem: { cx: 80, cy: 40 } }),
    }),
  }, 3), {
    centerX: 80,
    centerY: 40,
    indicatorCount: 3,
  });
});

test('pie selection stays available unless a view-mode data link would navigate', () => {
  assert.equal(pieSectorSelectedMode('view', 'data'), false);
  assert.equal(pieSectorSelectedMode('edit', 'data'), 'single');
  assert.equal(pieSectorSelectedMode('share', 'data'), 'single');
  assert.equal(pieSectorSelectedMode('view', 'title'), 'single');
});

test('navigation uses the prepared href', () => {
  let opened = '';
  const location = { href: '' };
  openPreparedInteractionNavigation(
    { href: '/cmdb/asset?screen=true', mode: 'sameFrame' },
    { open: (url) => { opened = url; }, location },
  );
  assert.equal(location.href, '/cmdb/asset?screen=true');
  assert.equal(opened, '');
  openPreparedInteractionNavigation(
    { href: 'https://example.com/item', mode: 'newTab' },
    { open: (url) => { opened = url; }, location },
  );
  assert.equal(opened, 'https://example.com/item');
});
