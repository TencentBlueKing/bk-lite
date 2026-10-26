import assert from 'node:assert/strict';
import { visibleMetricLines } from 'src/diagramOverlay/metricCard';

const view = { editorMode: 'EXPLORABLE_READONLY', lineCount: 2 };

assert.equal(visibleMetricLines({ ...view, zoom: 0.8, pinned: true, hovering: false }), true);
assert.equal(visibleMetricLines({ ...view, zoom: 0.7, pinned: true, hovering: false }), true);
assert.equal(visibleMetricLines({ ...view, zoom: 0.6, pinned: true, hovering: false }), false);
assert.equal(visibleMetricLines({ ...view, zoom: 0.6, pinned: true, hovering: true }), true);
assert.equal(visibleMetricLines({ ...view, zoom: 1, pinned: false, hovering: false }), false);
assert.equal(visibleMetricLines({ ...view, zoom: 1, pinned: false, hovering: true }), true);
assert.equal(visibleMetricLines({ editorMode: 'EDITABLE', zoom: 1, pinned: true, hovering: true, lineCount: 2 }), false);
assert.equal(visibleMetricLines({ ...view, zoom: 1, pinned: true, hovering: false, lineCount: 0 }), false);

console.log('metricCard ok');
