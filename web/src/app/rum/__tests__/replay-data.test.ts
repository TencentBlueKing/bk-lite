import { describe, expect, it, vi } from 'vitest';

import type { RumReplayManifest } from '@/app/rum/api';
import { loadReplayRecording, replayErrorMessage, RumReplayError } from '@/app/rum/sessions/lib/replay-data';

function baseManifest(overrides: Partial<RumReplayManifest> = {}): RumReplayManifest {
  return {
    state: 'ready',
    retentionDays: 7,
    recordings: [
      {
        recordingId: 'rec-1',
        segments: [
          {
            ref: 'seg-1',
            sequence: 0,
            compressedBytes: 10,
            uncompressedBytes: 20,
            eventCount: 2,
            hasFullSnapshot: true,
          },
        ],
      },
    ],
    ...overrides,
  } as RumReplayManifest;
}

describe('loadReplayRecording', () => {
  it('rejects empty recordings before fetching', async () => {
    await expect(
      loadReplayRecording(
        baseManifest({ recordings: [{ recordingId: 'rec-1', segments: [] } as never] }),
        'store',
        'sess',
        'rec-1',
        vi.fn(),
      ),
    ).rejects.toMatchObject({ name: 'RumReplayError', code: 'replay_empty' });
  });

  it('rejects grants that omit the target segment', async () => {
    const createReplayGrant = vi.fn().mockResolvedValue({
      targetIncluded: false,
      segments: [],
    });
    await expect(
      loadReplayRecording(baseManifest(), 'store', 'sess', 'rec-1', createReplayGrant),
    ).rejects.toMatchObject({ name: 'RumReplayError', code: 'replay_grant_missing' });
    expect(createReplayGrant).toHaveBeenCalledWith('store', 'sess', 'seg-1');
  });

  it('rejects unknown recording ids', async () => {
    await expect(
      loadReplayRecording(baseManifest(), 'store', 'sess', 'missing', vi.fn()),
    ).rejects.toBeInstanceOf(RumReplayError);
  });

  it('translates stable replay error codes', () => {
    const error = new RumReplayError('replay_empty');
    expect(replayErrorMessage(error, (key) => key)).toBe('rum.sessions.replayErrors.empty');
    expect(replayErrorMessage(new Error('raw'), (key, fallback) => fallback)).toBe(
      'Failed to read replay segment',
    );
  });
});
