import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acceptPreviewRawWrite,
  clearSampleKeyOnFetchFailure,
  isCurrentInteractionSample,
  nextInteractionSampleTicket,
  planInteractionSample,
  type InteractionSampleTicket,
} from '@/app/ops-analysis/utils/interactionSample';

const EMPTY: InteractionSampleTicket = { widgetId: '', sequence: 0 };

test('a later widget read invalidates the previous response', () => {
  const first = nextInteractionSampleTicket(EMPTY, 'widget-a');
  const readingA = nextInteractionSampleTicket(first, 'widget-a');
  const switched = nextInteractionSampleTicket(readingA, 'widget-b');

  assert.deepEqual(readingA, { widgetId: 'widget-a', sequence: 2 });
  assert.equal(isCurrentInteractionSample(switched, readingA), false);
  assert.equal(isCurrentInteractionSample(readingA, readingA), true);
  assert.equal(
    isCurrentInteractionSample(nextInteractionSampleTicket(readingA, 'widget-a'), readingA),
    false,
  );
});

test('canvas data is used before init settles and does not request', () => {
  const rendered = [{ host: 'b-1' }];
  const plan = planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: null,
    rendered,
    sourceId: 9,
    fetchedKey: 'widget-a:9',
  });

  assert.deepEqual(plan, { type: 'use-rendered', data: rendered });
});

test('an unsettled widget does not fetch with the previous datasource', () => {
  assert.deepEqual(planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: null,
    rendered: undefined,
    sourceId: 9,
    fetchedKey: '',
  }), { type: 'skip' });
});

test('a settled widget fetches once, then keeps that sample key', () => {
  const first = planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: 'widget-b',
    rendered: undefined,
    sourceId: 4,
    fetchedKey: '',
  });
  assert.deepEqual(first, { type: 'fetch', sampleKey: 'widget-b:4' });

  assert.deepEqual(planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: 'widget-b',
    rendered: undefined,
    sourceId: 4,
    fetchedKey: 'widget-b:4',
  }), { type: 'skip' });
});

test('closing, leaving the interaction page, or keeping a preview does not read again', () => {
  const base = {
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-a',
    settledWidgetId: 'widget-a',
    rendered: [{ host: 'a' }],
    sourceId: 1,
    fetchedKey: '',
  };
  assert.equal(planInteractionSample({ ...base, open: false }).type, 'skip');
  assert.equal(planInteractionSample({ ...base, interactionVisible: false }).type, 'skip');
  assert.equal(planInteractionSample({ ...base, hasPreview: true }).type, 'skip');
  assert.equal(planInteractionSample({ ...base, rendered: undefined, sourceId: null }).type, 'skip');
});

test('a failed sample fetch clears the key so the next open can retry', () => {
  const current = nextInteractionSampleTicket(EMPTY, 'widget-b');
  const cleared = clearSampleKeyOnFetchFailure(current, current, 'widget-b:4');
  assert.equal(cleared, '');
  assert.deepEqual(planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: 'widget-b',
    rendered: undefined,
    sourceId: 4,
    fetchedKey: cleared,
  }), { type: 'fetch', sampleKey: 'widget-b:4' });

  const newer = nextInteractionSampleTicket(current, 'widget-c');
  assert.equal(
    clearSampleKeyOnFetchFailure(newer, current, 'widget-c:8'),
    'widget-c:8',
  );
});

test('a stale preview ticket cannot write raw data back', () => {
  const reading = nextInteractionSampleTicket(EMPTY, 'widget-a');
  const switched = nextInteractionSampleTicket(reading, 'widget-b');

  assert.equal(acceptPreviewRawWrite(reading, reading), true);
  assert.equal(acceptPreviewRawWrite(switched, reading), false);
  assert.equal(acceptPreviewRawWrite(switched, undefined), false);
});

test('switching widgets drops the in-flight sample and the next widget can load its own', () => {
  let current = nextInteractionSampleTicket(EMPTY, 'widget-a');
  current = nextInteractionSampleTicket(current, 'widget-a');
  const responseA = current;
  current = nextInteractionSampleTicket(current, 'widget-b');
  const fetchedKey = '';

  assert.equal(isCurrentInteractionSample(current, responseA), false);
  assert.deepEqual(planInteractionSample({
    open: true,
    interactionVisible: true,
    hasPreview: false,
    widgetId: 'widget-b',
    settledWidgetId: 'widget-b',
    rendered: undefined,
    sourceId: 'src-b',
    fetchedKey,
  }), { type: 'fetch', sampleKey: 'widget-b:src-b' });
});
