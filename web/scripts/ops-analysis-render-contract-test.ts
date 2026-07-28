import assert from 'node:assert/strict';
import {
  DASHBOARD_RENDER_EVENT,
  buildDashboardRenderSignal,
  emitDashboardRenderSignal,
  hasRenderableWidgetData,
  type DashboardWidgetRenderResult,
} from '../src/app/ops-analysis/renderContract';

const results = (
  values: DashboardWidgetRenderResult[],
) => new Map(values.map((value) => [value.widgetId, value]));

assert.equal(hasRenderableWidgetData([]), false);
assert.equal(hasRenderableWidgetData({ items: [] }), false);
assert.equal(hasRenderableWidgetData([{ count: 1 }]), true);
assert.equal(hasRenderableWidgetData({ items: [{ count: 1 }] }), true);

assert.equal(
  buildDashboardRenderSignal(
    1,
    ['chart', 'table'],
    results([{ widgetId: 'chart', status: 'ready' }]),
  ),
  null,
  'missing widget must keep the dashboard pending',
);

assert.equal(
  buildDashboardRenderSignal(
    1,
    ['chart', 'table'],
    results([
      { widgetId: 'chart', status: 'ready' },
      { widgetId: 'table', status: 'loading' },
    ]),
  ),
  null,
  'loading widget must keep the dashboard pending',
);

const ready = buildDashboardRenderSignal(
  1,
  ['chart', 'table', 'empty', 'static', 'collapsed'],
  results([
    { widgetId: 'chart', status: 'ready' },
    { widgetId: 'table', status: 'ready' },
    { widgetId: 'empty', status: 'empty' },
    { widgetId: 'static', status: 'ready' },
    { widgetId: 'collapsed', status: 'empty' },
  ]),
);
assert.equal(ready?.type, 'report-ready');
assert.equal(ready?.widgets.find((item) => item.widgetId === 'empty')?.status, 'empty');

const failed = buildDashboardRenderSignal(
  1,
  ['chart', 'failed'],
  results([
    { widgetId: 'chart', status: 'ready' },
    { widgetId: 'failed', status: 'failed', error: 'fixture failure' },
  ]),
);
assert.equal(failed?.type, 'report-failed');
assert.equal(failed?.widgetId, 'failed');
assert.equal(failed?.error, 'fixture failure');

const dispatched: Array<{ type: string; detail: unknown }> = [];
const previousWindow = globalThis.window;
const previousCustomEvent = globalThis.CustomEvent;

class TestCustomEvent<T> {
  constructor(
    public type: string,
    public init: { detail: T },
  ) {}

  get detail() {
    return this.init.detail;
  }
}

Object.assign(globalThis, {
  CustomEvent: TestCustomEvent,
  window: {
    dispatchEvent(event: TestCustomEvent<unknown>) {
      dispatched.push({ type: event.type, detail: event.detail });
      return true;
    },
  },
});

emitDashboardRenderSignal(ready!);
assert.deepEqual(dispatched, [
  { type: DASHBOARD_RENDER_EVENT, detail: ready },
]);
assert.equal(
  Object.keys(globalThis.window).some((key) => key.startsWith('__BK_REPORT_')),
  false,
  'render contract must not publish debug state on window',
);

Object.assign(globalThis, {
  CustomEvent: previousCustomEvent,
  window: previousWindow,
});

console.log('ops-analysis render contract passed');
