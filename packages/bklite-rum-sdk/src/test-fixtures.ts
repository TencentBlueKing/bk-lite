import {
  type EventEvent,
  type Meta,
  type TraceEvent,
  type TransportItem,
  TransportItemType,
} from '@grafana/faro-web-sdk';

export const baseMeta = {
  app: {
    name: 'checkout',
    environment: 'production',
    release: '2026.07.15',
  },
  sdk: { name: '@grafana/faro-web-sdk', version: '2.8.2' },
  session: { id: 'session-01', attributes: { isSampled: 'true' } },
  page: { url: 'https://shop.example.test/checkout?token=secret#payment' },
  user: {
    id: 'user-pseudonym',
    email: 'must-not-leave@example.test',
    username: 'must-not-leave',
    fullName: 'Must Not Leave',
  },
  view: { name: '/checkout' },
} satisfies Meta;

export function eventItem(
  name: string,
  attributes: Record<string, string> = {},
): TransportItem<EventEvent> {
  return {
    type: TransportItemType.EVENT,
    meta: structuredClone(baseMeta),
    payload: {
      name,
      timestamp: '2026-07-15T08:00:00.000Z',
      attributes,
    },
  };
}

export function replayItem(
  event: Record<string, unknown>,
  timestamp = '2026-07-15T08:00:00.000Z',
): TransportItem<EventEvent> {
  return {
    type: TransportItemType.EVENT,
    meta: structuredClone(baseMeta),
    payload: {
      name: 'faro.session_recording.event',
      timestamp,
      attributes: { event: JSON.stringify(event) },
    },
  };
}

export function replayMetaItem(
  timestamp = 1,
  href = 'https://shop.example.test/checkout?token=secret#payment',
): TransportItem<EventEvent> {
  return replayItem({
    type: 4,
    timestamp,
    data: { href, width: 1440, height: 900 },
  });
}

export function traceItem(): TransportItem<TraceEvent> {
  return {
    type: TransportItemType.TRACE,
    meta: structuredClone(baseMeta),
    payload: {
      resourceSpans: [
        {
          resource: { attributes: [], droppedAttributesCount: 0 },
          scopeSpans: [],
          schemaUrl: undefined,
        },
      ],
    },
  };
}
