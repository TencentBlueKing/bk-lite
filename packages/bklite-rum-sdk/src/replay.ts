import {
  type EventEvent,
  type TransportItem,
  TransportItemType,
} from '@grafana/faro-web-sdk';

export const FARO_REPLAY_EVENT = 'faro.session_recording.event';
export const FARO_REPLAY_PAUSED_EVENT = 'faro.session_recording.paused';
export const FARO_REPLAY_STARTED_EVENT = 'faro.session_recording.started';
export const FARO_REPLAY_RESUMED_EVENT = 'faro.session_recording.resumed';

export interface ReplaySegmentOptions {
  recordingId: string;
  firstSequence: number;
  maxEvents: number;
  targetDurationMs?: number;
  targetUncompressedBytes: number;
  maxCompressedBytes?: number;
  maxEventBytes?: number;
  maxUncompressedBytes?: number;
  onDrop?: (reason: 'event-too-large' | 'segment-too-large') => void;
}

export interface ReplaySegment {
  application: string;
  body: Uint8Array;
  checksum: string;
  compressedBytes: number;
  endMs: number;
  eventCount: number;
  hasFullSnapshot: boolean;
  recordingId: string;
  segmentId: string;
  sequence: number;
  sessionId: string;
  startMs: number;
  uncompressedBytes: number;
}

interface ParsedReplayItem {
  application: string;
  environment?: string;
  event: Record<string, unknown>;
  pageId?: string;
  release?: string;
  sessionId: string;
  userId: string;
}

const REPLAY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function eventPayload(item: TransportItem): EventEvent | undefined {
  if (item.type !== TransportItemType.EVENT) return undefined;
  return item.payload as EventEvent;
}

export function isReplayEvent(item: TransportItem): boolean {
  const payload = eventPayload(item);
  if (payload?.name !== FARO_REPLAY_EVENT) return false;
  const serialized = payload.attributes?.event;
  if (!serialized) return false;

  try {
    const event = JSON.parse(serialized);
    return (
      typeof event === 'object' &&
      event !== null &&
      typeof event.timestamp === 'number'
    );
  } catch {
    return false;
  }
}

export function isReplayReservedEvent(item: TransportItem): boolean {
  const name = eventPayload(item)?.name;
  return typeof name === 'string' && name.startsWith('faro.session_recording.');
}

export function isReplayBoundaryEvent(item: TransportItem): boolean {
  const name = eventPayload(item)?.name;
  return (
    name === FARO_REPLAY_STARTED_EVENT || name === FARO_REPLAY_RESUMED_EVENT
  );
}

function parseReplayItem(item: TransportItem): ParsedReplayItem {
  if (!isReplayEvent(item)) {
    throw new TypeError('invalid Faro Replay event');
  }

  const payload = item.payload as EventEvent;
  const application = item.meta.app?.name?.trim();
  const sessionId = item.meta.session?.id?.trim();
  const userId = item.meta.user?.id?.trim();
  if (!application || !sessionId) {
    throw new TypeError('Replay requires non-empty app.name and session.id');
  }
  if (userId && !REPLAY_ID_PATTERN.test(userId)) {
    throw new TypeError(
      'Replay user.id must be a safe pseudonymous identifier',
    );
  }

  return {
    application,
    environment: item.meta.app?.environment,
    event: normalizeCanonical(JSON.parse(payload.attributes!.event!)) as Record<
      string,
      unknown
    >,
    pageId: item.meta.page?.id,
    release: item.meta.app?.release ?? item.meta.app?.version,
    sessionId,
    userId: userId ?? '',
  };
}

const utf8Encoder = new TextEncoder();

// Well-formed strings are returned unchanged. Rebuilding every scalar with
// repeated concatenation is quadratic and stalls the >4MiB Replay discard path.
function normalizeUnicodeScalars(value: string): string {
  let rewriteAt = -1;
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        index += 1;
        continue;
      }
      rewriteAt = index;
      break;
    }
    if (unit >= 0xdc00 && unit <= 0xdfff) {
      rewriteAt = index;
      break;
    }
  }
  if (rewriteAt < 0) return value;

  const parts: string[] = [];
  let cursor = 0;
  for (let index = rewriteAt; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        index += 1;
        continue;
      }
      parts.push(value.slice(cursor, index), '\ufffd');
      cursor = index + 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      parts.push(value.slice(cursor, index), '\ufffd');
      cursor = index + 1;
    }
  }
  parts.push(value.slice(cursor));
  return parts.join('');
}

function compareUtf8(left: string, right: string): number {
  const leftBytes = utf8Encoder.encode(left);
  const rightBytes = utf8Encoder.encode(right);
  const length = Math.min(leftBytes.length, rightBytes.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftBytes[index]! - rightBytes[index]!;
    if (difference !== 0) return difference;
  }
  return leftBytes.length - rightBytes.length;
}

function encodeJsonString(value: string): string {
  return JSON.stringify(normalizeUnicodeScalars(value))
    .replaceAll('\u2028', '\\u2028')
    .replaceAll('\u2029', '\\u2029');
}

function normalizeCanonical(value: unknown): unknown {
  if (typeof value === 'string') return normalizeUnicodeScalars(value);
  if (Array.isArray(value)) {
    return value.map((entry) => normalizeCanonical(entry));
  }
  if (value && typeof value === 'object') {
    const entries: Array<[string, unknown]> = Object.entries(value)
      .filter(([, entry]) => entry !== undefined)
      .map(([key, entry]): [string, unknown] => [
        normalizeUnicodeScalars(key),
        normalizeCanonical(entry),
      ])
      .sort(([left], [right]) => compareUtf8(left, right));
    return Object.fromEntries(entries);
  }
  return value;
}

export function canonicalStringify(value: unknown): string {
  const normalized = normalizeCanonical(value);
  if (normalized === null) return 'null';
  if (typeof normalized === 'string') return encodeJsonString(normalized);
  if (typeof normalized === 'number' || typeof normalized === 'boolean') {
    return JSON.stringify(normalized);
  }
  if (Array.isArray(normalized)) {
    return `[${normalized.map((entry) => canonicalStringify(entry)).join(',')}]`;
  }
  if (typeof normalized === 'object') {
    const entries = Object.entries(normalized).sort(([left], [right]) =>
      compareUtf8(left, right),
    );
    return `{${entries
      .map(
        ([key, entry]) =>
          `${encodeJsonString(key)}:${canonicalStringify(entry)}`,
      )
      .join(',')}}`;
  }
  throw new TypeError('canonical JSON only supports JSON values');
}

interface ReplayEnvelopeMaterial {
  schema_version: 1;
  application: string;
  environment: string;
  release: string;
  session_id: string;
  user_id?: string;
  page_id: string;
  recording_id: string;
  segment_id: string;
  sequence: number;
  started_at: string;
  ended_at: string;
  has_full_snapshot: boolean;
  event_count: number;
  events: Record<string, unknown>[];
}

function encodeReplayEnvelope(
  material: ReplayEnvelopeMaterial,
  checksum?: string,
): string {
  // Keep this insertion order aligned with the Go receiver's struct order.
  // Build it manually because JSON.stringify reorders integer-like nested
  // keys regardless of insertion order. Nested maps use UTF-8 byte ordering,
  // matching Go encoding/json.
  const entries: Array<[string, unknown]> = [
    ['schema_version', material.schema_version],
    ['application', material.application],
    ['environment', material.environment],
    ['release', material.release],
    ['session_id', material.session_id],
    ...(material.user_id
      ? ([['user_id', material.user_id]] as Array<[string, unknown]>)
      : []),
    ['page_id', material.page_id],
    ['recording_id', material.recording_id],
    ['segment_id', material.segment_id],
    ['sequence', material.sequence],
    ['started_at', material.started_at],
    ['ended_at', material.ended_at],
    ['has_full_snapshot', material.has_full_snapshot],
    ['event_count', material.event_count],
    ...(checksum
      ? ([['checksum_sha256', checksum]] as Array<[string, unknown]>)
      : []),
    ['events', material.events],
  ];
  return `{${entries
    .map(
      ([key, value]) => `${encodeJsonString(key)}:${canonicalStringify(value)}`,
    )
    .join(',')}}`;
}

async function sha256Hex(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Web Crypto is required by bklite-rum-sdk');
  }
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

async function gzip(value: string): Promise<Uint8Array> {
  if (typeof CompressionStream === 'undefined') {
    throw new Error('CompressionStream is required for Faro Replay');
  }

  const bytes = new TextEncoder().encode(value);
  const stream = new ReadableStream<BufferSource>({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  }).pipeThrough(new CompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function chunkReplayItems(
  items: ParsedReplayItem[],
  firstSequence: number,
  maxEvents: number,
  targetDurationMs: number,
  targetUncompressedBytes: number,
  maxEventBytes: number,
  maxUncompressedBytes: number,
  onDrop?: ReplaySegmentOptions['onDrop'],
): ParsedReplayItem[][] | undefined {
  const chunks: ParsedReplayItem[][] = [];
  const accepted: Array<{ bytes: number; item: ParsedReplayItem }> = [];
  for (const item of items) {
    const bytes = new TextEncoder().encode(
      canonicalStringify(item.event),
    ).byteLength;
    if (bytes > maxEventBytes || bytes > maxUncompressedBytes) {
      onDrop?.('event-too-large');
      return undefined;
    }
    accepted.push({ bytes, item });
  }

  let current: ParsedReplayItem[] = [];
  let currentBytes = 0;
  let currentStartMs = 0;
  let startIndex = 0;

  const startsWithCheckpoint =
    accepted[0]?.item.event.type === 4 && accepted[1]?.item.event.type === 2;
  if (firstSequence === 0 && !startsWithCheckpoint) return [];
  if (startsWithCheckpoint) {
    const checkpoint = accepted.slice(0, 2);
    current = checkpoint.map(({ item }) => item);
    currentBytes = checkpoint.reduce((total, { bytes }) => total + bytes, 0);
    if (currentBytes > maxUncompressedBytes) {
      onDrop?.('segment-too-large');
      return undefined;
    }
    currentStartMs = Number(current[0]?.event.timestamp ?? 0);
    startIndex = 2;
  }

  for (let index = startIndex; index < accepted.length; index += 1) {
    const { bytes: eventBytes, item } = accepted[index]!;
    if (item.event.type === 4) {
      const fullSnapshot = accepted[index + 1];
      if (fullSnapshot?.item.event.type !== 2) return [];
      if (current.length > 0) chunks.push(current);
      current = [item, fullSnapshot.item];
      currentBytes = eventBytes + fullSnapshot.bytes;
      if (currentBytes > maxUncompressedBytes) {
        onDrop?.('segment-too-large');
        return undefined;
      }
      currentStartMs = Number(item.event.timestamp);
      index += 1;
      continue;
    }
    if (item.event.type === 2) return [];
    const eventTimestamp = Number(item.event.timestamp);

    if (
      current.length > 0 &&
      (current.length >= maxEvents ||
        currentBytes + eventBytes > targetUncompressedBytes ||
        eventTimestamp - currentStartMs >= targetDurationMs)
    ) {
      chunks.push(current);
      current = [];
      currentBytes = 0;
    }
    if (current.length === 0) currentStartMs = eventTimestamp;
    current.push(item);
    currentBytes += eventBytes;
  }

  if (current.length > 0) chunks.push(current);
  return chunks;
}

export async function buildReplaySegments(
  items: TransportItem[],
  options: ReplaySegmentOptions,
): Promise<ReplaySegment[]> {
  if (items.length === 0) return [];
  if (!Number.isInteger(options.maxEvents) || options.maxEvents < 1) {
    throw new RangeError('maxEvents must be a positive integer');
  }
  const targetDurationMs = options.targetDurationMs ?? 5_000;
  const maxCompressedBytes = options.maxCompressedBytes ?? 1024 * 1024;
  const maxEventBytes = options.maxEventBytes ?? 4 * 1024 * 1024;
  const maxUncompressedBytes = options.maxUncompressedBytes ?? 4 * 1024 * 1024;
  for (const [name, value] of Object.entries({
    targetDurationMs,
    targetUncompressedBytes: options.targetUncompressedBytes,
    maxCompressedBytes,
    maxEventBytes,
    maxUncompressedBytes,
  })) {
    if (!Number.isInteger(value) || value < 1) {
      throw new RangeError(`${name} must be a positive integer`);
    }
  }
  if (options.targetUncompressedBytes > maxUncompressedBytes) {
    throw new RangeError(
      'targetUncompressedBytes cannot exceed maxUncompressedBytes',
    );
  }

  const parsed = items.map(parseReplayItem);
  const first = parsed[0]!;
  if (
    parsed.some(
      (item) =>
        item.application !== first.application ||
        item.sessionId !== first.sessionId ||
        item.userId !== first.userId,
    )
  ) {
    throw new TypeError(
      'Replay segment cannot mix applications, sessions, or users',
    );
  }

  const chunks = chunkReplayItems(
    parsed,
    options.firstSequence,
    options.maxEvents,
    targetDurationMs,
    options.targetUncompressedBytes,
    maxEventBytes,
    maxUncompressedBytes,
    options.onDrop,
  );
  if (!chunks) return [];
  const segments: ReplaySegment[] = [];

  for (let index = 0; index < chunks.length; index += 1) {
    const chunk = chunks[index]!;
    const sequence = options.firstSequence + segments.length;
    const events = chunk.map((item) => item.event);
    const startMs = Math.min(...events.map((event) => Number(event.timestamp)));
    const endMs = Math.max(...events.map((event) => Number(event.timestamp)));
    const hasFullSnapshot = events.some((event) => event.type === 2);
    const eventDigest = await sha256Hex(canonicalStringify(events));
    const segmentId = await sha256Hex(
      canonicalStringify({
        application: first.application,
        eventDigest,
        recordingId: options.recordingId,
        sequence,
        sessionId: first.sessionId,
        userId: first.userId,
      }),
    );
    const material: ReplayEnvelopeMaterial = {
      schema_version: 1,
      application: first.application,
      environment: first.environment ?? '',
      release: first.release ?? '',
      session_id: first.sessionId,
      user_id: first.userId,
      page_id: first.pageId?.trim() || options.recordingId,
      recording_id: options.recordingId,
      segment_id: segmentId,
      sequence,
      started_at: new Date(startMs).toISOString(),
      ended_at: new Date(endMs).toISOString(),
      has_full_snapshot: hasFullSnapshot,
      event_count: events.length,
      events,
    };
    const checksum = await sha256Hex(encodeReplayEnvelope(material));
    const envelope = encodeReplayEnvelope(material, checksum);
    const uncompressedBytes = new TextEncoder().encode(envelope).byteLength;
    if (uncompressedBytes > maxUncompressedBytes) {
      options.onDrop?.('segment-too-large');
      return [];
    }
    const body = await gzip(envelope);
    if (body.byteLength > maxCompressedBytes) {
      options.onDrop?.('segment-too-large');
      return [];
    }

    segments.push({
      application: first.application,
      body,
      checksum,
      compressedBytes: body.byteLength,
      endMs,
      eventCount: events.length,
      hasFullSnapshot,
      recordingId: options.recordingId,
      segmentId,
      sequence,
      sessionId: first.sessionId,
      startMs,
      uncompressedBytes,
    });
  }

  return segments;
}
