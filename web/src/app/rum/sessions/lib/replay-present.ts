import type { RumReplayManifest } from '@/app/rum/api';

export type RumReplayRecording = RumReplayManifest['recordings'][number];

const SNAPSHOT_ONLY_MS = 1000;

/** Parse replay index / envelope wall times (ISO or space-separated, optional Z). */
export function parseReplayTime(value: string | undefined | null): number | null {
  const raw = (value || '').trim();
  if (!raw) return null;
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`;
  const ms = Date.parse(withZone);
  return Number.isFinite(ms) ? ms : null;
}

export function formatReplayClock(value: string | null | undefined): string {
  if (!value) return '—';
  const ms = parseReplayTime(value);
  if (ms === null) return value;
  return new Date(ms).toLocaleString();
}

/** Playable span from recording segment wall times (index metadata, no blob fetch). */
export function recordingPlayableMs(recording: RumReplayRecording): number {
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const segment of recording.segments || []) {
    const s = parseReplayTime(segment.startedAt);
    const e = parseReplayTime(segment.endedAt);
    if (s !== null) start = Math.min(start, s);
    if (e !== null) end = Math.max(end, e);
  }
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return 0;
  return end - start;
}

export function eventsPlayableMs(events: unknown[]): number {
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const event of events) {
    if (!event || typeof event !== 'object' || !('timestamp' in event)) continue;
    const ts = (event as { timestamp?: unknown }).timestamp;
    if (typeof ts !== 'number' || !Number.isFinite(ts)) continue;
    start = Math.min(start, ts);
    end = Math.max(end, ts);
  }
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return 0;
  return end - start;
}

export function isSnapshotOnly(playableMs: number): boolean {
  return playableMs < SNAPSHOT_ONLY_MS;
}

export function presentReplayRecording(recording: RumReplayRecording, index: number) {
  const playableMs = recordingPlayableMs(recording);
  const eventCount = (recording.segments || []).reduce((sum, seg) => sum + (seg.eventCount || 0), 0);
  let startedAt: string | null = null;
  let earliest = Number.POSITIVE_INFINITY;
  for (const segment of recording.segments || []) {
    const s = parseReplayTime(segment.startedAt);
    if (s !== null && s < earliest) {
      earliest = s;
      startedAt = segment.startedAt || null;
    }
  }
  return {
    ordinal: index + 1,
    playableMs,
    snapshotOnly: isSnapshotOnly(playableMs),
    eventCount,
    segmentCount: recording.segments?.length || 0,
    startedAt,
    shortId: (recording.recordingId || '').slice(0, 8),
  };
}
