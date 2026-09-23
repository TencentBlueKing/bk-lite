import { randomBytes } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { createCollectBatch } from './batches';
import {
  eventItem,
  replayItem,
  replayMetaItem,
  traceItem,
} from './test-fixtures';
import { CoreRumTransport } from './transport';
import { initializeFaro } from '@grafana/faro-web-sdk';
import { afterEach, describe, expect, it, vi } from 'vitest';

describe('CoreRumTransport', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('flushes the real Faro tail batch on hidden before pagehide and the long send timeout', async () => {
    const replayCalls: RequestInit[] = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) replayCalls.push(init ?? {});
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => 'recording-fixed',
    });
    const faro = initializeFaro({
      app: { name: 'checkout', environment: 'test', release: '2026.07.15' },
      batching: { enabled: true, itemLimit: 3, sendTimeout: 60_000 },
      instrumentations: [],
      isolate: true,
      sessionTracking: { enabled: false },
      transports: [transport],
    });
    expect(faro).toBeDefined();
    faro!.api.setSession({ id: 'session-01' });
    faro!.api.setPage({
      id: 'page-01',
      url: 'https://shop.example.test/checkout',
    });
    faro!.api.setUser({ id: 'user-pseudonym' });

    const pushReplay = (event: Record<string, unknown>) => {
      faro!.api.pushEvent('faro.session_recording.event', {
        event: JSON.stringify(event),
      });
    };
    pushReplay({
      type: 4,
      timestamp: 1,
      data: {
        href: 'https://shop.example.test/checkout',
        width: 1440,
        height: 900,
      },
    });
    pushReplay({ type: 2, timestamp: 2, data: { node: { id: 1 } } });
    faro!.api.pushEvent('faro.session_recording.started', {});
    await vi.waitFor(() => expect(replayCalls).toHaveLength(1));

    pushReplay({ type: 3, timestamp: 3, data: { source: 1 } });
    expect(replayCalls).toHaveLength(1);

    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));
    await vi.waitFor(() => expect(replayCalls).toHaveLength(2));

    window.dispatchEvent(new Event('pagehide'));
    await Promise.resolve();
    expect(replayCalls).toHaveLength(2);
    const tail = JSON.parse(
      gunzipSync(
        new Uint8Array(await new Response(replayCalls[1]?.body).arrayBuffer()),
      ).toString('utf8'),
    );
    expect(tail).toMatchObject({ sequence: 1, event_count: 1 });
    expect(replayCalls[1]?.keepalive).toBe(true);
    faro!.transports.pause();
  });

  it.each([
    ['omitted', undefined],
    ['false', { enabled: false }],
  ] as const)(
    'does not collect or send Replay when the transport option is %s',
    async (_, replay) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 202 }));
      const transport = new CoreRumTransport({
        collectUrl: 'https://rum.example.test/rum/v1/collect',
        replayUrl: 'https://rum.example.test/rum/v1/replay',
        apiKey: 'obk_public',
        fetch: fetcher,
        ...(replay ? { replay } : {}),
        sleep: async () => {},
      });

      await transport.send([
        replayMetaItem(),
        replayItem({ type: 2, timestamp: 1 }),
        eventItem('faro.session_recording.started'),
      ]);
      await transport.flushReplay();

      expect(fetcher).not.toHaveBeenCalled();
    },
  );

  it('stages Faro split Meta until its FullSnapshot without a false snapshot warning', async () => {
    const envelopes: Array<{
      events: Array<{ type: number }>;
      sequence: number;
    }> = [];
    const debug = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      debug,
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });

    await transport.send(replayMetaItem(1));
    expect(envelopes).toEqual([]);

    await transport.send(replayItem({ type: 2, timestamp: 2 }));
    expect(envelopes).toEqual([
      expect.objectContaining({
        sequence: 0,
        events: [
          expect.objectContaining({ type: 4 }),
          expect.objectContaining({ type: 2 }),
        ],
      }),
    ]);
    expect(debug).not.toHaveBeenCalled();
  });

  it('sends ordinary and trace payloads as one collect request with one batch id', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
    });

    await transport.send([eventItem('view_changed'), traceItem()]);

    expect(fetcher).toHaveBeenCalledTimes(1);
    const init = fetcher.mock.calls[0]?.[1];
    const body = JSON.parse(String(init?.body));
    const headers = new Headers(init?.headers);
    expect(body.events).toHaveLength(1);
    expect(body.traces.resourceSpans).toHaveLength(1);
    expect(headers.get('x-api-key')).toBe('obk_public');
    expect(headers.get('x-rum-application')).toBe('checkout');
    expect(headers.get('x-rum-batch-id')).toMatch(/^[a-f0-9-]+$/);
    expect(headers.has('x-rum-request-class')).toBe(false);
    expect(init?.credentials).toBe('omit');
    expect(init?.referrerPolicy).toBe('no-referrer');
  });

  it('splits ordinary collect requests before the one MiB edge body limit', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
    });

    await transport.send([
      eventItem('custom.large', { payload: 'x'.repeat(600_000) }),
      eventItem('custom.large', { payload: 'y'.repeat(600_000) }),
    ]);

    expect(fetcher).toHaveBeenCalledTimes(2);
    const bodies = fetcher.mock.calls.map(([, init]) => String(init?.body));
    expect(
      bodies.every(
        (body) => new TextEncoder().encode(body).byteLength <= 1_000_000,
      ),
    ).toBe(true);
    expect(
      bodies.map((body) => JSON.parse(body).events[0].attributes.payload[0]),
    ).toEqual(['x', 'y']);
    expect(
      fetcher.mock.calls.map(([, init]) =>
        new Headers(init?.headers).get('x-rum-batch-id'),
      ),
    ).toHaveLength(2);
  });

  it('splits traces by their serialized body before the one MiB edge limit', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
    });
    const first = traceItem();
    const second = traceItem();
    first.payload.resourceSpans![0]!.resource!.attributes.push({
      key: 'payload',
      value: { stringValue: 'x'.repeat(600_000) },
    });
    second.payload.resourceSpans![0]!.resource!.attributes.push({
      key: 'payload',
      value: { stringValue: 'y'.repeat(600_000) },
    });
    const combinedBody = JSON.stringify(
      createCollectBatch([first, second]).body,
    );
    expect(new TextEncoder().encode(combinedBody).byteLength).toBeGreaterThan(
      1_000_000,
    );

    await transport.send([first, second]);

    expect(fetcher).toHaveBeenCalledTimes(2);
    const bodies = fetcher.mock.calls.map(([, init]) => String(init?.body));
    expect(
      bodies.every(
        (body) => new TextEncoder().encode(body).byteLength < 1_000_000,
      ),
    ).toBe(true);
    expect(
      bodies.map(
        (body) =>
          JSON.parse(body).traces.resourceSpans[0].resource.attributes[0].value
            .stringValue[0],
      ),
    ).toEqual(['x', 'y']);
    expect(
      fetcher.mock.calls.every(([, init]) =>
        new Headers(init?.headers).has('x-rum-request-class'),
      ),
    ).toBe(false);
  });

  it('drops a single collect item that cannot fit the edge request budget', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
      debug,
    });

    await expect(
      transport.send(
        eventItem('custom.too-large', { payload: 'x'.repeat(1_100_000) }),
      ),
    ).resolves.toBeUndefined();

    expect(fetcher).not.toHaveBeenCalled();
    expect(debug).toHaveBeenCalledWith({
      channel: 'ordinary',
      reason: 'event-too-large',
    });
  });

  it('extracts Replay events from collect and posts gzip segments to replay', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => 'recording-fixed',
    });

    await transport.send([
      replayMetaItem(),
      replayItem({ type: 2, timestamp: 1 }),
      eventItem('faro.session_recording.started'),
    ]);

    expect(fetcher).toHaveBeenCalledTimes(1);
    const replayCall = fetcher.mock.calls.find(([url]) =>
      String(url).endsWith('/replay'),
    );
    const replayBody = new Uint8Array(
      await new Response(replayCall?.[1]?.body).arrayBuffer(),
    );
    const envelope = JSON.parse(gunzipSync(replayBody).toString('utf8'));
    expect(envelope.recording_id).toBe('recording-fixed');
    expect(envelope.user_id).toBe('user-pseudonym');
    expect(
      envelope.events.map((event: { type: number }) => event.type),
    ).toEqual([4, 2]);
    const replayHeaders = new Headers(replayCall?.[1]?.headers);
    expect(replayHeaders.get('content-encoding')).toBe('gzip');
    expect(replayHeaders.get('content-type')).toBe(
      'application/vnd.weops.rum-replay.v1+json',
    );
    expect(replayHeaders.get('x-faro-session-id')).toBe('session-01');
    expect(replayHeaders.get('x-rum-application')).toBe('checkout');
    expect(replayCall?.[1]?.credentials).toBe('omit');
    expect(replayCall?.[1]?.referrerPolicy).toBe('no-referrer');
  });

  it('rejects malformed reserved Replay items without poisoning ordinary telemetry', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      debug,
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });
    const malformedReplay = replayItem({ type: 2, timestamp: 1 });
    malformedReplay.payload.attributes = {};

    await transport.send([eventItem('view_changed'), malformedReplay]);

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, request] = fetcher.mock.calls[0]!;
    expect(String(url)).toMatch(/\/collect$/);
    expect(JSON.parse(String(request?.body)).events).toMatchObject([
      { name: 'view_changed' },
    ]);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'invalid-item',
    });
  });

  it.each([200, 204])(
    'does not advance Replay sequence when the receiver returns protocol status %s',
    async (status) => {
      const sequences: number[] = [];
      const debug = vi.fn();
      const fetcher = vi
        .fn<typeof fetch>()
        .mockImplementation(async (url, init) => {
          if (!String(url).endsWith('/replay'))
            return new Response(null, { status: 202 });
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          sequences.push(
            JSON.parse(gunzipSync(body).toString('utf8')).sequence,
          );
          return new Response(null, { status });
        });
      const transport = new CoreRumTransport({
        collectUrl: 'https://rum.example.test/rum/v1/collect',
        replayUrl: 'https://rum.example.test/rum/v1/replay',
        apiKey: 'obk_public',
        debug,
        fetch: fetcher,
        replay: { enabled: true },
        sleep: async () => {},
        randomId: () => 'recording-fixed',
      });

      await transport.send([
        replayMetaItem(1),
        replayItem({ type: 2, timestamp: 2 }),
        eventItem('faro.session_recording.started'),
      ]);
      await transport.send(
        replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
      );
      await transport.flushReplay();

      expect(sequences).toEqual([0]);
      expect(debug).toHaveBeenCalledWith({
        channel: 'replay',
        reason: 'request-failed',
      });
    },
  );

  it('accumulates forty 250ms Faro flushes into bounded five-second Replay segments', async () => {
    const envelopes: Array<{
      sequence: number;
      events: Array<{ timestamp: number; type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => 'recording-fixed',
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    for (let index = 0; index < 40; index += 1) {
      await transport.send(
        replayItem({
          type: 3,
          timestamp: 3 + index * 250,
          data: { source: 1 },
        }),
      );
    }
    await transport.flushReplay();

    expect(envelopes[0]?.events.map(({ type }) => type)).toEqual([4, 2]);
    expect(envelopes.slice(1)).toHaveLength(2);
    expect(
      envelopes
        .flatMap(({ events }) => events)
        .filter(({ type }) => type === 3),
    ).toHaveLength(40);
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1, 2]);
  });

  it('aligns every periodic Meta and FullSnapshot checkpoint at a segment boundary', async () => {
    const envelopes: Array<{
      sequence: number;
      events: Array<{ type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => 'recording-fixed',
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    await transport.send(replayMetaItem(4));
    await transport.send(replayItem({ type: 2, timestamp: 5 }));

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1, 2]);
    expect(
      envelopes.map(({ events }) => events.map(({ type }) => type)),
    ).toEqual([[4, 2], [3], [4, 2]]);
  });

  it('flushes a sparse Replay accumulator after five seconds', async () => {
    vi.useFakeTimers();
    try {
      const envelopes: Array<{ sequence: number }> = [];
      const fetcher = vi
        .fn<typeof fetch>()
        .mockImplementation(async (url, init) => {
          if (String(url).endsWith('/replay')) {
            const body = new Uint8Array(
              await new Response(init?.body).arrayBuffer(),
            );
            envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
          }
          return new Response(null, { status: 202 });
        });
      const transport = new CoreRumTransport({
        collectUrl: 'https://rum.example.test/rum/v1/collect',
        replayUrl: 'https://rum.example.test/rum/v1/replay',
        apiKey: 'obk_public',
        fetch: fetcher,
        replay: { enabled: true },
        sleep: async () => {},
      });

      await transport.send([
        replayMetaItem(1),
        replayItem({ type: 2, timestamp: 2 }),
      ]);
      await transport.send(
        replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
      );
      expect(envelopes.map(({ sequence }) => sequence)).toEqual([0]);

      await vi.advanceTimersByTimeAsync(5_000);
      await transport.flushReplay();

      expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1]);
    } finally {
      vi.useRealTimers();
    }
  });

  it('flushes pending Replay work with keepalive on pagehide', async () => {
    const replayCalls: RequestInit[] = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) replayCalls.push(init ?? {});
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    expect(replayCalls).toHaveLength(1);

    window.dispatchEvent(new Event('pagehide'));
    await vi.waitFor(() => expect(replayCalls).toHaveLength(2));

    expect(replayCalls[1]?.keepalive).toBe(true);
  });

  it('reports an oversized pagehide Replay flush as best effort without keepalive', async () => {
    const replayCalls: RequestInit[] = [];
    const debug = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) replayCalls.push(init ?? {});
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      debug,
      fetch: fetcher,
      replay: { enabled: true, targetSegmentBytes: 512 * 1024 },
      sleep: async () => {},
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(
      replayItem({
        type: 3,
        timestamp: 3,
        data: { source: 1, text: randomBytes(90_000).toString('base64') },
      }),
    );
    expect(replayCalls).toHaveLength(1);

    window.dispatchEvent(new Event('pagehide'));
    await vi.waitFor(() => expect(replayCalls).toHaveLength(2));

    expect(replayCalls[1]?.body).toBeInstanceOf(Uint8Array);
    expect((replayCalls[1]?.body as Uint8Array).byteLength).toBeGreaterThan(
      60_000,
    );
    expect(replayCalls[1]?.keepalive).toBe(false);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'pagehide-keepalive-unavailable',
    });
  });

  it('keeps a new scope Meta after the retired recording flush fails', async () => {
    const envelopes: Array<{ sequence: number; session_id: string }> = [];
    let settleRetiredFlush: ((response: Response) => void) | undefined;
    let replayCalls = 0;
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (!String(url).endsWith('/replay'))
          return new Response(null, { status: 202 });
        replayCalls += 1;
        const body = new Uint8Array(
          await new Response(init?.body).arrayBuffer(),
        );
        envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        if (replayCalls === 2) {
          return new Promise<Response>((resolve) => {
            settleRetiredFlush = resolve;
          });
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    const nextMeta = replayMetaItem(4);
    nextMeta.meta.session!.id = 'session-02';
    let rolloverSettled = false;
    const rollover = transport.send(nextMeta).then(() => {
      rolloverSettled = true;
    });
    await vi.waitFor(() => expect(settleRetiredFlush).toBeDefined());
    await Promise.resolve();
    expect(rolloverSettled).toBe(false);

    settleRetiredFlush?.(new Response(null, { status: 400 }));
    await rollover;
    const nextSnapshot = replayItem({ type: 2, timestamp: 5 });
    nextSnapshot.meta.session!.id = 'session-02';
    await transport.send(nextSnapshot);

    expect(envelopes.at(-1)).toMatchObject({
      session_id: 'session-02',
      sequence: 0,
    });
  });

  it('does not let a retired recording failure unregister the active scope pagehide flush', async () => {
    const envelopes: Array<{
      events: Array<{ type: number }>;
      session_id: string;
    }> = [];
    let settleRetiredFlush: ((response: Response) => void) | undefined;
    let replayCalls = 0;
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (!String(url).endsWith('/replay'))
          return new Response(null, { status: 202 });
        replayCalls += 1;
        const body = new Uint8Array(
          await new Response(init?.body).arrayBuffer(),
        );
        envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        if (replayCalls === 2) {
          return new Promise<Response>((resolve) => {
            settleRetiredFlush = resolve;
          });
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    const nextMeta = replayMetaItem(4);
    const nextSnapshot = replayItem({ type: 2, timestamp: 5 });
    nextMeta.meta.session!.id = 'session-02';
    nextSnapshot.meta.session!.id = 'session-02';
    const rollover = transport.send([nextMeta, nextSnapshot]);
    await vi.waitFor(() => expect(settleRetiredFlush).toBeDefined());
    const nextIncremental = replayItem({
      type: 3,
      timestamp: 6,
      data: { source: 1 },
    });
    nextIncremental.meta.session!.id = 'session-02';
    await transport.send(nextIncremental);

    settleRetiredFlush?.(new Response(null, { status: 400 }));
    await rollover;
    await vi.waitFor(() =>
      expect(
        envelopes.some(({ session_id }) => session_id === 'session-02'),
      ).toBe(true),
    );
    window.dispatchEvent(new Event('pagehide'));
    await vi.waitFor(() =>
      expect(
        envelopes.some(
          ({ events, session_id }) =>
            session_id === 'session-02' && events[0]?.type === 3,
        ),
      ).toBe(true),
    );
  });

  it('uses a 1000-event default guard so normal dynamic pages stay within the manifest budget', async () => {
    const envelopes: Array<{ events: Array<{ type: number }> }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    for (let index = 0; index < 1_000; index += 1) {
      await transport.send(
        replayItem({ type: 3, timestamp: 3, data: { source: 1, id: index } }),
      );
    }
    await transport.flushReplay();

    expect(envelopes).toHaveLength(2);
    expect(envelopes[1]?.events).toHaveLength(1_000);
  });

  it('drops missing, unsafe, or mixed Faro applications without rejecting into Faro', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
      debug,
    });
    const missing = eventItem('view_changed');
    missing.meta.app!.name = ' ';
    const unsafe = eventItem('view_changed');
    unsafe.meta.app!.name = 'checkout\nspoofed';
    const other = traceItem();
    other.meta.app!.name = 'admin';

    await expect(transport.send(missing)).resolves.toBeUndefined();
    await expect(transport.send(unsafe)).resolves.toBeUndefined();
    await expect(
      transport.send([eventItem('view_changed'), other]),
    ).resolves.toBeUndefined();
    expect(fetcher).not.toHaveBeenCalled();
    expect(debug).toHaveBeenCalledWith({
      channel: 'ordinary',
      reason: 'invalid-item',
    });
  });

  it('quarantines a recording after an unconfirmed segment and restarts only at a new snapshot boundary', async () => {
    let replayCalls = 0;
    const replayEnvelopes: Array<{ recording_id: string; sequence: number }> =
      [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/collect'))
          return new Response(null, { status: 202 });
        replayCalls += 1;
        const body = new Uint8Array(
          await new Response(init?.body).arrayBuffer(),
        );
        replayEnvelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        return new Response(null, { status: replayCalls === 2 ? 400 : 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
      randomId: () => `id-${++random}`,
      replay: { enabled: true, maxSegmentEvents: 1 },
    });

    await expect(
      transport.send([
        replayMetaItem(),
        replayItem({ type: 2, timestamp: 1 }),
        eventItem('faro.session_recording.started'),
        replayItem({ type: 3, timestamp: 2, data: { source: 1 } }),
      ]),
    ).resolves.toBeUndefined();
    expect(replayEnvelopes.map(({ sequence }) => sequence)).toEqual([0, 1]);

    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    expect(replayCalls).toBe(2);

    await transport.send([
      replayMetaItem(4),
      replayItem({ type: 2, timestamp: 4 }),
      eventItem('faro.session_recording.started'),
    ]);
    expect(replayEnvelopes.at(-1)).toMatchObject({ sequence: 0 });
    expect(replayEnvelopes.at(-1)?.recording_id).not.toBe(
      replayEnvelopes[0]?.recording_id,
    );
  });

  it('quarantines an oversized sequence-zero bootstrap until a new checkpoint', async () => {
    const envelopes: Array<{ recording_id: string; sequence: number }> = [];
    const debug = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
      debug,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({
        type: 2,
        timestamp: 2,
        data: { node: 'x'.repeat(4 * 1024 * 1024 + 1) },
      }),
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    ]);

    const failed = (
      transport as unknown as {
        recordings: Map<string, { failed: boolean; recordingId: string }>;
      }
    ).recordings.get('session-01');
    expect(failed).toMatchObject({ failed: true });
    expect(envelopes).toEqual([]);

    await transport.send(
      replayItem({ type: 3, timestamp: 4, data: { source: 1 } }),
    );
    expect(envelopes).toEqual([]);

    await transport.send(replayItem({ type: 2, timestamp: 5 }));
    expect(envelopes).toEqual([]);

    await transport.send([
      replayMetaItem(6),
      replayItem({ type: 2, timestamp: 7 }),
    ]);
    expect(envelopes).toEqual([expect.objectContaining({ sequence: 0 })]);
    expect(envelopes[0]?.recording_id).not.toBe(failed?.recordingId);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'event-too-large',
    });
  });

  it('quarantines an oversized nonzero mutation and never uploads later sequences', async () => {
    const envelopes: Array<{ recording_id: string; sequence: number }> = [];
    const debug = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
      debug,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    const firstRecordingId = envelopes[0]?.recording_id;
    await transport.send([
      replayItem({
        type: 3,
        timestamp: 3,
        data: { source: 1, text: 'x'.repeat(4 * 1024 * 1024 + 1) },
      }),
      replayItem({ type: 3, timestamp: 4, data: { source: 1 } }),
    ]);

    const failed = (
      transport as unknown as {
        recordings: Map<string, { failed: boolean }>;
      }
    ).recordings.get('session-01');
    expect(failed).toMatchObject({ failed: true });
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0]);

    await transport.send(
      replayItem({ type: 3, timestamp: 5, data: { source: 1 } }),
    );
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0]);

    await transport.send([
      replayMetaItem(6),
      replayItem({ type: 2, timestamp: 7 }),
    ]);
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 0]);
    expect(envelopes[1]?.recording_id).not.toBe(firstRecordingId);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'event-too-large',
    });
  });

  it('keeps only the active browser session recording state', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
    });
    const firstMeta = replayMetaItem(1);
    const first = replayItem({ type: 2, timestamp: 1 });
    const secondMeta = replayMetaItem(2);
    const second = replayItem({ type: 2, timestamp: 2 });
    secondMeta.meta.session!.id = 'session-02';
    second.meta.session!.id = 'session-02';

    await transport.send([firstMeta, first]);
    await transport.send([secondMeta, second]);

    const state = transport as unknown as { recordings: Map<string, unknown> };
    expect([...state.recordings.keys()]).toEqual(['session-02']);
  });

  it('keeps Meta and FullSnapshot together when Faro dispatches Replay one item at a time', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      events: Array<{ type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send(replayMetaItem(1));
    await transport.send(replayItem({ type: 2, timestamp: 2 }));
    await transport.send(eventItem('faro.session_recording.started'));
    await transport.send(
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
    );
    await transport.flushReplay();

    expect(envelopes).toHaveLength(2);
    expect(envelopes[0]?.events.map(({ type }) => type)).toEqual([4, 2]);
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1]);
    expect(
      new Set(envelopes.map(({ recording_id }) => recording_id)).size,
    ).toBe(1);
  });

  it('starts a new recording on Replay resume but not on a periodic FullSnapshot checkout', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      events: Array<{ type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send([
      replayMetaItem(3),
      replayItem({ type: 2, timestamp: 3 }),
    ]);
    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1]);
    expect(
      new Set(envelopes.map(({ recording_id }) => recording_id)).size,
    ).toBe(1);

    await transport.send(eventItem('faro.session_recording.paused'));
    await transport.send(replayMetaItem(4));
    await transport.send(replayItem({ type: 2, timestamp: 5 }));
    expect(envelopes).toHaveLength(2);
    await transport.send(eventItem('faro.session_recording.resumed'));
    await transport.send(
      replayItem({ type: 3, timestamp: 6, data: { source: 1 } }),
    );
    await transport.flushReplay();

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1, 0, 1]);
    expect(envelopes[2]?.events.map(({ type }) => type)).toEqual([4, 2]);
    expect(envelopes[2]?.recording_id).not.toBe(envelopes[0]?.recording_id);
    expect(envelopes[3]?.recording_id).toBe(envelopes[2]?.recording_id);
  });

  it('rotates an already-active recording when resume and snapshot share one Faro batch', async () => {
    const envelopes: Array<{ recording_id: string; sequence: number }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(eventItem('faro.session_recording.paused'));
    await transport.send([
      replayMetaItem(3),
      replayItem({ type: 2, timestamp: 4 }),
      eventItem('faro.session_recording.resumed'),
    ]);

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 0]);
    expect(envelopes[1]?.recording_id).not.toBe(envelopes[0]?.recording_id);
  });

  it('flushes replay events before a same-batch pause into the old recording', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      events: Array<{ timestamp: number; type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send([
      replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
      eventItem('faro.session_recording.paused'),
      replayMetaItem(4),
      replayItem({ type: 2, timestamp: 5 }),
      eventItem('faro.session_recording.resumed'),
    ]);

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1, 0]);
    expect(envelopes[1]?.events.map(({ timestamp }) => timestamp)).toEqual([3]);
    expect(envelopes[1]?.recording_id).toBe(envelopes[0]?.recording_id);
    expect(envelopes[2]?.recording_id).not.toBe(envelopes[0]?.recording_id);
    expect(envelopes[2]?.events.map(({ type }) => type)).toEqual([4, 2]);
  });

  it('clears a stale paused scope after session rollover before the next same-batch restart', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      session_id: string;
      events: Array<{ timestamp: number; type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(eventItem('faro.session_recording.paused'));

    const rolloverMeta = replayMetaItem(3);
    const rolloverSnapshot = replayItem({ type: 2, timestamp: 4 });
    const rolloverResumed = eventItem('faro.session_recording.resumed');
    for (const item of [rolloverMeta, rolloverSnapshot, rolloverResumed]) {
      item.meta.session!.id = 'session-02';
    }
    await transport.send([rolloverMeta, rolloverSnapshot]);
    await transport.send(rolloverResumed);

    const oldIncremental = replayItem({
      type: 3,
      timestamp: 5,
      data: { source: 1 },
    });
    const paused = eventItem('faro.session_recording.paused');
    const nextMeta = replayMetaItem(6);
    const nextSnapshot = replayItem({ type: 2, timestamp: 7 });
    const resumed = eventItem('faro.session_recording.resumed');
    for (const item of [
      oldIncremental,
      paused,
      nextMeta,
      nextSnapshot,
      resumed,
    ]) {
      item.meta.session!.id = 'session-02';
    }
    await transport.send([
      oldIncremental,
      paused,
      nextMeta,
      nextSnapshot,
      resumed,
    ]);

    expect(
      envelopes.map(({ session_id, sequence }) => `${session_id}:${sequence}`),
    ).toEqual(['session-01:0', 'session-02:0', 'session-02:1', 'session-02:0']);
    expect(envelopes[2]?.events.map(({ timestamp }) => timestamp)).toEqual([5]);
    expect(envelopes[2]?.recording_id).toBe(envelopes[1]?.recording_id);
    expect(envelopes[3]?.recording_id).not.toBe(envelopes[1]?.recording_id);
  });

  it('keeps periodic Meta and FullSnapshot checkouts in the active recording', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      events: Array<{ type: number }>;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send([
      replayMetaItem(3),
      replayItem({ type: 2, timestamp: 4 }),
    ]);
    await transport.send(
      replayItem({ type: 3, timestamp: 5, data: { source: 1 } }),
    );
    await transport.flushReplay();

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 1, 2]);
    expect(envelopes[1]?.events.map(({ type }) => type)).toEqual([4, 2]);
    expect(
      new Set(envelopes.map(({ recording_id }) => recording_id)).size,
    ).toBe(1);
  });

  it('binds a paused Replay restart to an identity changed before resume', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      user_id?: string;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    await transport.send(eventItem('faro.session_recording.paused'));
    const nextMeta = replayMetaItem(3);
    const nextSnapshot = replayItem({ type: 2, timestamp: 4 });
    const resumed = eventItem('faro.session_recording.resumed');
    const incremental = replayItem({
      type: 3,
      timestamp: 5,
      data: { source: 1 },
    });
    for (const item of [nextMeta, nextSnapshot, resumed, incremental]) {
      item.meta.user!.id = 'user-second';
      await transport.send(item);
    }
    await transport.flushReplay();

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 0, 1]);
    expect(envelopes.map(({ user_id }) => user_id)).toEqual([
      'user-pseudonym',
      'user-second',
      'user-second',
    ]);
    expect(envelopes[1]?.recording_id).not.toBe(envelopes[0]?.recording_id);
    expect(envelopes[2]?.recording_id).toBe(envelopes[1]?.recording_id);
  });

  it('drops a new-session incremental stream until a FullSnapshot can start sequence zero', async () => {
    const envelopes: Array<{
      session_id: string;
      sequence: number;
      events: Array<{ type: number }>;
    }> = [];
    const debug = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      debug,
    });

    await transport.send([
      replayMetaItem(1),
      replayItem({ type: 2, timestamp: 2 }),
    ]);
    const rollover = replayItem({ type: 3, timestamp: 3, data: { source: 1 } });
    rollover.meta.session!.id = 'session-02';
    await transport.send(rollover);
    expect(envelopes).toHaveLength(1);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'snapshot-required',
    });

    const rolloverMeta = replayMetaItem(4);
    rolloverMeta.meta.session!.id = 'session-02';
    await transport.send(rolloverMeta);
    const checkpoint = replayItem({ type: 2, timestamp: 4 });
    checkpoint.meta.session!.id = 'session-02';
    await transport.send(checkpoint);
    expect(envelopes.at(-1)).toMatchObject({
      session_id: 'session-02',
      sequence: 0,
    });
    expect(envelopes.at(-1)?.events.map(({ type }) => type)).toEqual([4, 2]);
  });

  it('starts a new snapshot-rooted recording whenever user identity changes', async () => {
    const envelopes: Array<{
      recording_id: string;
      sequence: number;
      user_id?: string;
    }> = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) => {
        if (String(url).endsWith('/replay')) {
          const body = new Uint8Array(
            await new Response(init?.body).arrayBuffer(),
          );
          envelopes.push(JSON.parse(gunzipSync(body).toString('utf8')));
        }
        return new Response(null, { status: 202 });
      });
    let random = 0;
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      replay: { enabled: true },
      sleep: async () => {},
      randomId: () => `recording-${++random}`,
      debug,
    });

    const anonymousMeta = replayMetaItem(1);
    const anonymousSnapshot = replayItem({ type: 2, timestamp: 2 });
    anonymousMeta.meta.user = undefined;
    anonymousSnapshot.meta.user = undefined;
    await transport.send([anonymousMeta, anonymousSnapshot]);

    const loginIncremental = replayItem({
      type: 3,
      timestamp: 3,
      data: { source: 1 },
    });
    await transport.send(loginIncremental);
    expect(envelopes).toHaveLength(1);

    await transport.send(replayMetaItem(4));
    await transport.send(replayItem({ type: 2, timestamp: 4 }));

    const logoutIncremental = replayItem({
      type: 3,
      timestamp: 5,
      data: { source: 1 },
    });
    logoutIncremental.meta.user = undefined;
    await transport.send(logoutIncremental);
    expect(envelopes).toHaveLength(2);
    const logoutMeta = replayMetaItem(6);
    logoutMeta.meta.user = undefined;
    await transport.send(logoutMeta);
    const logoutSnapshot = replayItem({ type: 2, timestamp: 6 });
    logoutSnapshot.meta.user = undefined;
    await transport.send(logoutSnapshot);

    const secondUserIncremental = replayItem({
      type: 3,
      timestamp: 7,
      data: { source: 1 },
    });
    secondUserIncremental.meta.user!.id = 'user-second';
    await transport.send(secondUserIncremental);
    expect(envelopes).toHaveLength(3);
    const secondUserMeta = replayMetaItem(8);
    secondUserMeta.meta.user!.id = 'user-second';
    await transport.send(secondUserMeta);
    const secondUserSnapshot = replayItem({ type: 2, timestamp: 8 });
    secondUserSnapshot.meta.user!.id = 'user-second';
    await transport.send(secondUserSnapshot);

    expect(envelopes.map(({ sequence }) => sequence)).toEqual([0, 0, 0, 0]);
    expect(envelopes.map(({ user_id }) => user_id)).toEqual([
      undefined,
      'user-pseudonym',
      undefined,
      'user-second',
    ]);
    expect(
      new Set(envelopes.map(({ recording_id }) => recording_id)).size,
    ).toBe(4);
    expect(debug).toHaveBeenCalledWith({
      channel: 'replay',
      reason: 'snapshot-required',
    });
  });

  it('shares one pending keepalive byte budget across concurrent requests and retries', async () => {
    const releases: Array<(response: Response) => void> = [];
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          releases.push(resolve);
        }),
    );
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: fetcher,
      sleep: async () => {},
    });
    const first = eventItem('custom.large', { payload: 'x'.repeat(35_000) });
    const second = eventItem('custom.large', { payload: 'y'.repeat(35_000) });

    const sends = [transport.send(first), transport.send(second)];
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher.mock.calls.map(([, init]) => init?.keepalive)).toEqual([
      true,
      false,
    ]);
    for (const release of releases)
      release(new Response(null, { status: 202 }));
    await Promise.all(sends);
  });

  it('absorbs permanent request failures because Faro does not await transport promises', async () => {
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
      fetch: vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 400 })),
      sleep: async () => {},
      debug,
    });

    await expect(
      transport.send(eventItem('view_changed')),
    ).resolves.toBeUndefined();
    expect(debug).toHaveBeenCalledWith({
      channel: 'ordinary',
      reason: 'request-failed',
    });
  });

  it('uses collect and replay URLs as trace ignore targets', () => {
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/rum/v1/collect',
      replayUrl: 'https://rum.example.test/rum/v1/replay',
      apiKey: 'obk_public',
    });

    expect(transport.getIgnoreUrls()).toEqual([
      'https://rum.example.test/rum/v1/collect',
      'https://rum.example.test/rum/v1/replay',
    ]);
    expect(transport.isBatched()).toBe(true);
    expect(transport.name).toBe('bklite-rum-sdk');
    expect(transport.version).toBe('0.1.0');
  });

  it('uses the fixed gateway headers and accepts only 202', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 202 }));
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/collect',
      replayUrl: 'https://rum.example.test/replay',
      apiKey: 'public-key',
      debug,
      fetch: fetcher,
    });

    await transport.send(eventItem('view_changed'));

    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get('x-api-key')).toBe('public-key');
    expect(headers.get('x-rum-application')).toBe('checkout');
    expect(headers.get('x-rum-batch-id')).toBeTruthy();
    expect(headers.has('x-rum-request-class')).toBe(false);
    expect(debug).not.toHaveBeenCalled();
  });

  it('does not accept HTTP 200 as a successful gateway response', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    const debug = vi.fn();
    const transport = new CoreRumTransport({
      collectUrl: 'https://rum.example.test/collect',
      replayUrl: 'https://rum.example.test/replay',
      apiKey: 'public-key',
      debug,
      fetch: fetcher,
      sleep: async () => {},
    });

    await transport.send(eventItem('view_changed'));

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(debug).toHaveBeenCalledWith({
      channel: 'ordinary',
      reason: 'request-failed',
    });
  });
});
