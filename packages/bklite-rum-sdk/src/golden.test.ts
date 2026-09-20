import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  BaseTransport,
  EVENT_SESSION_EXTEND,
  EVENT_SESSION_RESUME,
  EVENT_SESSION_START,
  EVENT_VIEW_CHANGED,
  getTransportBody,
  initializeFaro,
  LogLevel,
  type TransportItem,
  TransportItemType,
} from '@grafana/faro-web-sdk';
import { describe, expect, it } from 'vitest';

class CaptureTransport extends BaseTransport {
  readonly name = 'golden-capture';
  readonly version = 'test';
  readonly captured: TransportItem[] = [];

  getIgnoreUrls() {
    return [];
  }

  isBatched() {
    return false;
  }

  send(items: TransportItem | TransportItem[]) {
    this.captured.push(...(Array.isArray(items) ? items : [items]));
  }
}

const GOLDEN_PATH = resolve(
  import.meta.dirname,
  '../testdata/faro-2.8.2-golden.json',
);
const GOLDEN_TIMESTAMP_MS = Date.parse('2026-07-15T08:00:00.000Z');

function stableTransportBody(items: TransportItem[]) {
  const body = getTransportBody(items);
  const meta = body.meta;
  // Golden corpus models the JSON wire body, where undefined object members
  // are omitted. Comparing the in-memory SDK object would pin incidental
  // JavaScript properties that never cross the network.
  return JSON.parse(
    JSON.stringify({
      ...body,
      meta: {
        app: {
          name: meta.app?.name,
          environment: meta.app?.environment,
          release: meta.app?.release,
        },
        sdk: { name: meta.sdk?.name, version: meta.sdk?.version },
        session: { id: meta.session?.id },
        page: { id: meta.page?.id, url: meta.page?.url },
        view: { name: meta.view?.name },
        user: { id: meta.user?.id },
      },
    }),
  );
}

function buildGoldenCorpus() {
  const transport = new CaptureTransport();
  const faro = initializeFaro({
    app: { name: 'checkout', environment: 'test', release: '2026.07.15' },
    instrumentations: [],
    transports: [transport],
    sessionTracking: { enabled: false },
    isolate: true,
  });
  faro.api.setSession({ id: 'session-golden' });
  faro.api.setPage({
    id: 'page-golden',
    url: 'https://shop.example.test/checkout?token=secret',
  });
  faro.api.setView({ name: 'checkout' });
  faro.api.setUser({ id: 'user-golden' });

  faro.api.pushLog(['checkout warning'], {
    context: { component: 'checkout' },
    level: LogLevel.WARN,
    timestampOverwriteMs: GOLDEN_TIMESTAMP_MS,
  });
  const error = new Error('payment failed');
  error.name = 'TypeError';
  faro.api.pushError(error, {
    context: { component: 'checkout' },
    fingerprint: 'payment-submit',
    stackFrames: [
      {
        filename: 'https://cdn.example.test/assets/checkout.js?v=7',
        function: 'submitPayment',
        lineno: 42,
        colno: 7,
      },
    ],
    timestampOverwriteMs: GOLDEN_TIMESTAMP_MS,
    type: 'TypeError',
  });
  faro.api.pushMeasurement(
    {
      type: 'web-vitals',
      values: { lcp: 1234.5 },
    },
    {
      context: { navigation_type: 'navigate', rating: 'good' },
      timestampOverwriteMs: GOLDEN_TIMESTAMP_MS,
    },
  );
  faro.api.pushEvent(
    EVENT_VIEW_CHANGED,
    { fromView: 'cart', toView: 'checkout' },
    undefined,
    {
      timestampOverwriteMs: GOLDEN_TIMESTAMP_MS,
    },
  );
  faro.api.pushTraces({
    resourceSpans: [
      {
        resource: {
          attributes: [
            { key: 'service.name', value: { stringValue: 'checkout' } },
          ],
          droppedAttributesCount: 0,
        },
        scopeSpans: [
          {
            scope: { name: 'golden', version: '1.0.0' },
            spans: [
              {
                traceId: '00112233445566778899aabbccddeeff',
                spanId: '0011223344556677',
                parentSpanId: '',
                name: 'GET /checkout',
                kind: 3,
                startTimeUnixNano: '1784102400000000000',
                endTimeUnixNano: '1784102400010000000',
                attributes: [],
                droppedAttributesCount: 0,
                events: [],
                droppedEventsCount: 0,
                links: [],
                droppedLinksCount: 0,
                status: { code: 0 },
              },
            ],
          },
        ],
      },
    ],
  } as Parameters<typeof faro.api.pushTraces>[0]);

  const ordinary = transport.captured.filter(
    (item) => item.type !== TransportItemType.TRACE,
  );
  const traces = transport.captured.filter(
    (item) => item.type === TransportItemType.TRACE,
  );
  return {
    generatedBy: '@grafana/faro-web-sdk@2.8.2',
    ordinary: stableTransportBody(ordinary),
    traces: stableTransportBody(traces),
  };
}

describe('Faro 2.8.2 golden transport corpus', () => {
  it('pins the official lifecycle event names consumed by the receiver', () => {
    expect({
      sessionExtend: EVENT_SESSION_EXTEND,
      sessionResume: EVENT_SESSION_RESUME,
      sessionStart: EVENT_SESSION_START,
      viewChanged: EVENT_VIEW_CHANGED,
    }).toEqual({
      sessionExtend: 'session_extend',
      sessionResume: 'session_resume',
      sessionStart: 'session_start',
      viewChanged: 'view_changed',
    });
  });

  it('captures the official log, exception, measurement and named-event shapes', () => {
    const transport = new CaptureTransport();
    const faro = initializeFaro({
      app: { name: 'checkout', environment: 'test', release: 'golden' },
      instrumentations: [],
      transports: [transport],
      sessionTracking: { enabled: false },
      isolate: true,
    });

    faro.api.pushLog(['hello'], { context: { source: 'golden' } });
    faro.api.pushError(new Error('boom'));
    faro.api.pushMeasurement({ type: 'web-vital', values: { lcp: 1234 } });
    faro.api.pushEvent('checkout.submit', { step: 'payment' });

    expect(transport.captured.map((item) => item.type)).toEqual([
      'log',
      'exception',
      'measurement',
      'event',
    ]);
    expect(
      transport.captured.every((item) => item.meta.app?.name === 'checkout'),
    ).toBe(true);
    expect(
      transport.captured.every((item) => item.meta.sdk?.version === '2.8.2'),
    ).toBe(true);
  });

  it('matches the shared exact-SDK corpus consumed by the Go receiver', () => {
    const actual = buildGoldenCorpus();
    expect(actual).toEqual(JSON.parse(readFileSync(GOLDEN_PATH, 'utf8')));
  });
});
