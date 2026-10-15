import type { RumReplayGrant, RumReplayManifest } from '@/app/rum/api';
import { rewriteRumSegmentUrl } from '@/app/rum/lib/format';

export class RumReplayError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = 'RumReplayError';
    this.code = code;
  }
}

const REPLAY_ERROR_KEYS: Record<string, [string, string]> = {
  replay_empty: ['rum.sessions.replayErrors.empty', 'Replay recording has no segments'],
  replay_grant_missing: ['rum.sessions.replayErrors.grantMissing', 'Replay grant does not include the target segment'],
  replay_segment_mismatch: ['rum.sessions.replayErrors.segmentMismatch', 'Replay segment does not match the manifest'],
  replay_out_of_order: ['rum.sessions.replayErrors.outOfOrder', 'Replay events are out of order'],
  replay_too_short: ['rum.sessions.replayErrors.tooShort', 'Replay recording has too few events'],
  replay_bad_timestamp: ['rum.sessions.replayErrors.badTimestamp', 'Invalid replay event timestamp'],
  replay_segment_too_large: ['rum.sessions.replayErrors.segmentTooLarge', 'Replay segment exceeds its declared size'],
  replay_segment_size: ['rum.sessions.replayErrors.segmentSize', 'Replay segment size does not match the manifest'],
  replay_checksum_unavailable: ['rum.sessions.replayErrors.checksumUnavailable', 'Replay checksum is unavailable'],
  replay_checksum_mismatch: ['rum.sessions.replayErrors.checksumMismatch', 'Replay segment checksum mismatch'],
  replay_denied: ['rum.sessions.replayErrors.denied', 'Replay data access denied'],
  replay_expired: ['rum.sessions.replayErrors.expired', 'Replay data expired'],
  replay_read_failed: ['rum.sessions.replayErrors.readFailed', 'Failed to read replay segment'],
  replay_content_type: ['rum.sessions.replayErrors.contentType', 'Unexpected replay segment content type'],
  replay_decompress_unavailable: ['rum.sessions.replayErrors.decompressUnavailable', 'Browser cannot decompress replay data'],
  replay_bad_envelope: ['rum.sessions.replayErrors.badEnvelope', 'Unexpected replay envelope format'],
};

function fail(code: string): never {
  throw new RumReplayError(code);
}

export function replayErrorMessage(
  error: unknown,
  translate: (key: string, fallback: string) => string,
): string {
  const code = error instanceof RumReplayError ? error.code : 'replay_read_failed';
  const entry = REPLAY_ERROR_KEYS[code] ?? REPLAY_ERROR_KEYS.replay_read_failed;
  return translate(entry[0], entry[1]);
}

const MAX_COMPRESSED_BYTES = 1 << 20;
const MAX_UNCOMPRESSED_BYTES = 4 << 20;
const ENVELOPE_KEYS = [
  'schema_version',
  'application',
  'environment',
  'release',
  'session_id',
  'page_id',
  'recording_id',
  'segment_id',
  'sequence',
  'started_at',
  'ended_at',
  'has_full_snapshot',
  'event_count',
  'checksum_sha256',
  'events',
] as const;

interface StoredEnvelope {
  schema_version: number;
  application: string;
  environment: string;
  release: string;
  session_id: string;
  page_id: string;
  recording_id: string;
  segment_id: string;
  sequence: number;
  started_at: string;
  ended_at: string;
  has_full_snapshot: boolean;
  event_count: number;
  checksum_sha256: string;
  events: unknown[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readBounded(stream: ReadableStream<Uint8Array>, expected: number, maximum: number) {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value?.byteLength) continue;
    total += value.byteLength;
    if (total > expected || total > maximum) {
      await reader.cancel();
      fail('replay_segment_too_large');
    }
    chunks.push(value);
  }
  if (total !== expected) fail('replay_segment_size');
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

function checksumMaterial(envelope: StoredEnvelope) {
  return JSON.stringify({
    schema_version: envelope.schema_version,
    application: envelope.application,
    environment: envelope.environment,
    release: envelope.release,
    session_id: envelope.session_id,
    page_id: envelope.page_id,
    recording_id: envelope.recording_id,
    segment_id: envelope.segment_id,
    sequence: envelope.sequence,
    started_at: envelope.started_at,
    ended_at: envelope.ended_at,
    has_full_snapshot: envelope.has_full_snapshot,
    event_count: envelope.event_count,
    events: envelope.events,
  })
    .replaceAll('\u2028', '\\u2028')
    .replaceAll('\u2029', '\\u2029');
}

async function sha256(value: string) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    fail('replay_checksum_unavailable');
  }
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function assertChecksum(envelope: StoredEnvelope) {
  // Grant URL + auth already gate access; skip hash only when WebCrypto is unavailable
  // (plain HTTP non-localhost).
  if (!globalThis.crypto?.subtle) return;
  if ((await sha256(checksumMaterial(envelope))) !== envelope.checksum_sha256) {
    fail('replay_checksum_mismatch');
  }
}

async function decodeSegment(
  url: string,
  authority: { application: string; session: string; recordingId: string },
  segment: RumReplayManifest['recordings'][number]['segments'][number],
  authToken?: string | null,
) {
  const headers: HeadersInit = {};
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const response = await fetch(rewriteRumSegmentUrl(url), {
    cache: 'no-store',
    credentials: 'same-origin',
    headers,
  });
  if (response.status === 401 || response.status === 403) {
    fail('replay_denied');
  }
  if (response.status === 410) fail('replay_expired');
  if (!response.ok || !response.body) fail('replay_read_failed');
  if (response.headers.get('content-type') !== 'application/octet-stream') {
    fail('replay_content_type');
  }
  const length = Number(response.headers.get('content-length'));
  if (length !== segment.compressedBytes || length > MAX_COMPRESSED_BYTES) {
    fail('replay_segment_size');
  }
  const compressed = await readBounded(response.body, length, MAX_COMPRESSED_BYTES);
  const stream = new Response(compressed).body;
  if (!stream) fail('replay_decompress_unavailable');
  const decoded = await readBounded(
    stream.pipeThrough(new DecompressionStream('gzip')),
    segment.uncompressedBytes,
    MAX_UNCOMPRESSED_BYTES,
  );
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(decoded);
  const value: unknown = JSON.parse(raw);
  if (
    !isRecord(value) ||
    Object.keys(value).length !== ENVELOPE_KEYS.length ||
    !Object.keys(value).every((key) => ENVELOPE_KEYS.includes(key as (typeof ENVELOPE_KEYS)[number]))
  ) {
    fail('replay_bad_envelope');
  }
  const envelope = value as unknown as StoredEnvelope;
  if (
    envelope.schema_version !== 1 ||
    envelope.application !== authority.application ||
    envelope.recording_id !== authority.recordingId ||
    envelope.sequence !== segment.sequence ||
    envelope.event_count !== segment.eventCount ||
    envelope.events.length !== segment.eventCount ||
    envelope.has_full_snapshot !== segment.hasFullSnapshot
  ) {
    fail('replay_segment_mismatch');
  }
  await assertChecksum(envelope);
  return envelope.events;
}

function eventTimestamp(value: unknown) {
  if (!isRecord(value) || typeof value.timestamp !== 'number' || !Number.isSafeInteger(value.timestamp)) {
    fail('replay_bad_timestamp');
  }
  return value.timestamp;
}

export async function loadReplayRecording(
  manifest: RumReplayManifest,
  application: string,
  session: string,
  recordingId: string,
  createReplayGrant: (
    application: string,
    session: string,
    targetRef: string,
  ) => Promise<RumReplayGrant>,
  authToken?: string | null,
) {
  const recording = manifest.recordings.find((item) => item.recordingId === recordingId);
  if (!recording?.segments.length) fail('replay_empty');
  const events: unknown[] = [];
  for (const segment of [...recording.segments].sort((a, b) => a.sequence - b.sequence)) {
    const grant = await createReplayGrant(application, session, segment.ref);
    const granted = grant.segments?.find((item) => item.ref === segment.ref);
    if (!grant.targetIncluded || !granted) {
      fail('replay_grant_missing');
    }
    events.push(
      ...(await decodeSegment(granted.url, { application, session, recordingId }, segment, authToken)),
    );
  }
  let previous = -1;
  for (const event of events) {
    const timestamp = eventTimestamp(event);
    if (timestamp < previous) fail('replay_out_of_order');
    previous = timestamp;
  }
  if (events.length < 2) fail('replay_too_short');
  return events;
}
