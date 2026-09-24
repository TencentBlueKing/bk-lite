import {
  getTransportBody,
  type Meta,
  type TraceEvent,
  type TransportBody,
  type TransportItem,
  TransportItemType,
} from '@grafana/faro-web-sdk';
import { isReplayReservedEvent } from './replay';

export interface ClassifiedItems {
  collect: TransportItem[];
  ordinary: TransportItem[];
  replay: TransportItem[];
  traces: TransportItem[];
}

export interface CollectBatch {
  body: TransportBody;
}

export function sanitizeMeta(meta: Meta): Meta {
  let page = meta.page;
  if (page?.url) {
    try {
      const url = new URL(page.url);
      page = { ...page, url: `${url.origin}${url.pathname}` };
    } catch {
      page = { ...page, url: undefined };
    }
  }

  const userId = meta.user?.id?.trim();
  return {
    ...meta,
    page,
    user: userId ? { id: userId } : undefined,
  };
}

export function classifyItems(items: TransportItem[]): ClassifiedItems {
  const result: ClassifiedItems = {
    collect: [],
    ordinary: [],
    replay: [],
    traces: [],
  };

  for (const item of items) {
    if (isReplayReservedEvent(item)) {
      result.replay.push(item);
    } else if (item.type === TransportItemType.TRACE) {
      result.collect.push(item);
      result.traces.push(item);
    } else {
      result.collect.push(item);
      result.ordinary.push(item);
    }
  }

  return result;
}

export function createCollectBatch(items: TransportItem[]): CollectBatch {
  if (items.length === 0) {
    throw new TypeError('collect batch cannot be empty');
  }

  const sanitized = items.map((item) => ({
    ...item,
    meta: sanitizeMeta(item.meta),
  }));
  const traces = sanitized.filter(
    (item) => item.type === TransportItemType.TRACE,
  );
  const ordinary = sanitized.filter(
    (item) => item.type !== TransportItemType.TRACE,
  );
  const body = getTransportBody(
    ordinary.length > 0 ? ordinary : traces.slice(0, 1),
  );
  if (traces.length > 0) {
    body.traces = {
      resourceSpans: traces.flatMap(
        (item) => (item.payload as TraceEvent).resourceSpans ?? [],
      ),
    };
  }
  return { body };
}
