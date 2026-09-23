import { describe, expect, it, vi } from 'vitest';

import type { RumReplayManifest } from '@/app/rum/api';
import { loadReplayRecording } from '@/app/rum/sessions/lib/replay-data';

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
    ).rejects.toThrow('回放录制为空');
  });

  it('rejects grants that omit the target segment', async () => {
    const createReplayGrant = vi.fn().mockResolvedValue({
      targetIncluded: false,
      segments: [],
    });
    await expect(
      loadReplayRecording(baseManifest(), 'store', 'sess', 'rec-1', createReplayGrant),
    ).rejects.toThrow('回放授权不包含目标分段');
    expect(createReplayGrant).toHaveBeenCalledWith('store', 'sess', 'seg-1');
  });

  it('rejects unknown recording ids', async () => {
    await expect(
      loadReplayRecording(baseManifest(), 'store', 'sess', 'missing', vi.fn()),
    ).rejects.toThrow('回放录制为空');
  });
});
