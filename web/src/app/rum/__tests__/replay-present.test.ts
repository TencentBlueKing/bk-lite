import { describe, expect, it } from 'vitest';

import {
  eventsPlayableMs,
  formatReplayClock,
  isSnapshotOnly,
  presentReplayRecording,
  recordingPlayableMs,
} from '@/app/rum/sessions/lib/replay-present';

describe('replay presentation helpers', () => {
  it('treats sub-second recordings as snapshot-only', () => {
    expect(isSnapshotOnly(0)).toBe(true);
    expect(isSnapshotOnly(999)).toBe(true);
    expect(isSnapshotOnly(1000)).toBe(false);
  });

  it('formats space-separated index times for the recording list', () => {
    expect(formatReplayClock(null)).toBe('—');
    expect(formatReplayClock('2026-09-22 05:59:10.307')).toMatch(/2026/);
  });

  it('computes playable ms from segment wall clocks including space-separated times', () => {
    expect(
      recordingPlayableMs({
        recordingId: 'rec-1',
        pageId: 'page-1',
        segments: [
          {
            sequence: 0,
            startedAt: '2026-09-22 05:59:10.307',
            endedAt: '2026-09-22 05:59:10.307',
            eventCount: 2,
            compressedBytes: 1,
            uncompressedBytes: 2,
            hasFullSnapshot: true,
            ref: 'a',
          },
          {
            sequence: 1,
            startedAt: '2026-09-22 05:59:10.342',
            endedAt: '2026-09-22 05:59:10.432',
            eventCount: 2,
            compressedBytes: 1,
            uncompressedBytes: 2,
            hasFullSnapshot: false,
            ref: 'b',
          },
        ],
      }),
    ).toBe(125);
  });

  it('computes playable ms from loaded rrweb events', () => {
    expect(eventsPlayableMs([{ timestamp: 1000 }, { timestamp: 3500 }])).toBe(2500);
    expect(eventsPlayableMs([{ type: 2 }])).toBe(0);
  });

  it('presents ordinal and snapshot-only without inventing a route', () => {
    const presented = presentReplayRecording(
      {
        recordingId: 'abcdef12-hhhh',
        pageId: 'page-uuid',
        segments: [
          {
            sequence: 0,
            startedAt: '2026-09-22T05:59:28.807Z',
            endedAt: '2026-09-22T05:59:28.807Z',
            eventCount: 2,
            compressedBytes: 1,
            uncompressedBytes: 2,
            hasFullSnapshot: true,
            ref: 'a',
          },
        ],
      },
      2,
    );
    expect(presented).toEqual({
      ordinal: 3,
      playableMs: 0,
      snapshotOnly: true,
      eventCount: 2,
      segmentCount: 1,
      startedAt: '2026-09-22T05:59:28.807Z',
      shortId: 'abcdef12',
    });
  });
});
