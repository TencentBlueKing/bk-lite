import { classifyItems, createCollectBatch, sanitizeMeta } from './batches';
import { eventItem, replayItem, traceItem } from './test-fixtures';
import { describe, expect, it } from 'vitest';

describe('Faro collect batches', () => {
  it('serializes ordinary items and traces into one Faro collect batch', () => {
    const { ordinary, traces, replay } = classifyItems([
      eventItem('view_changed'),
      traceItem(),
    ]);

    expect(ordinary).toHaveLength(1);
    expect(traces).toHaveLength(1);
    expect(replay).toHaveLength(0);
    expect(createCollectBatch([...ordinary, ...traces]).body).toMatchObject({
      events: [{ name: 'view_changed' }],
      traces: { resourceSpans: expect.any(Array) },
    });
  });

  it('removes identifiable user fields and URL query/fragment before egress', () => {
    const sanitized = sanitizeMeta(eventItem('view_changed').meta);

    expect(sanitized.user).toEqual({ id: 'user-pseudonym' });
    expect(sanitized.page?.url).toBe('https://shop.example.test/checkout');
  });

  it('preserves one sanitized metadata envelope for a mixed collect batch', () => {
    const batch = createCollectBatch([
      eventItem('view_changed'),
      traceItem(),
    ]).body;

    expect(batch.meta.app?.name).toBe('checkout');
    expect(batch.meta.page?.url).toBe(
      'https://shop.example.test/checkout',
    );
    expect(batch.events).toHaveLength(1);
    expect(batch.traces?.resourceSpans).toHaveLength(1);
  });

  it('routes every reserved Replay name away from an otherwise valid ordinary batch', () => {
    const malformedReplay = replayItem({ type: 2, timestamp: 1 });
    malformedReplay.payload.attributes = {};
    const lifecycle = eventItem('faro.session_recording.started');

    const { ordinary, replay } = classifyItems([
      eventItem('view_changed'),
      malformedReplay,
      lifecycle,
    ]);

    expect(ordinary.map((item) => item.payload)).toMatchObject([
      { name: 'view_changed' },
    ]);
    expect(replay).toEqual([malformedReplay, lifecycle]);
  });
});
