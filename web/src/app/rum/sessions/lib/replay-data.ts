import type { RumReplayGrant, RumReplayManifest } from '@/app/rum/api';
import { rewriteRumSegmentUrl } from '@/app/rum/lib/format';

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
      throw new Error('Replay segment exceeds its declared size');
    }
    chunks.push(value);
  }
  if (total !== expected) throw new Error('Replay segment size does not match the manifest');
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
    throw new Error('当前环境无法校验回放分段');
  }
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function assertChecksum(envelope: StoredEnvelope) {
  // Grant URL + auth already gate access; skip hash only when WebCrypto is unavailable
  // (plain HTTP non-localhost).
  if (!globalThis.crypto?.subtle) return;
  if ((await sha256(checksumMaterial(envelope))) !== envelope.checksum_sha256) {
    throw new Error('回放分段校验失败');
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
  if (response.status === 401 || response.status === 403) throw new Error('没有回放数据访问权限');
  if (response.status === 410) throw new Error('回放数据已过期');
  if (!response.ok || !response.body) throw new Error('回放分段读取失败');
  if (response.headers.get('content-type') !== 'application/octet-stream') {
    throw new Error('回放分段格式不正确');
  }
  const length = Number(response.headers.get('content-length'));
  if (length !== segment.compressedBytes || length > MAX_COMPRESSED_BYTES) {
    throw new Error('回放分段大小不正确');
  }
  const compressed = await readBounded(response.body, length, MAX_COMPRESSED_BYTES);
  const stream = new Response(compressed).body;
  if (!stream) throw new Error('浏览器无法解压回放数据');
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
    throw new Error('回放信封格式不正确');
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
    throw new Error('回放分段与索引不一致');
  }
  await assertChecksum(envelope);
  return envelope.events;
}

function eventTimestamp(value: unknown) {
  if (!isRecord(value) || typeof value.timestamp !== 'number' || !Number.isSafeInteger(value.timestamp)) {
    throw new Error('回放事件时间无效');
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
  if (!recording?.segments.length) throw new Error('回放录制为空');
  const events: unknown[] = [];
  for (const segment of [...recording.segments].sort((a, b) => a.sequence - b.sequence)) {
    const grant = await createReplayGrant(application, session, segment.ref);
    const granted = grant.segments?.find((item) => item.ref === segment.ref);
    if (!grant.targetIncluded || !granted) throw new Error('回放授权不包含目标分段');
    events.push(
      ...(await decodeSegment(granted.url, { application, session, recordingId }, segment, authToken)),
    );
  }
  let previous = -1;
  for (const event of events) {
    const timestamp = eventTimestamp(event);
    if (timestamp < previous) throw new Error('回放事件顺序无效');
    previous = timestamp;
  }
  if (events.length < 2) throw new Error('回放事件不足');
  return events;
}
