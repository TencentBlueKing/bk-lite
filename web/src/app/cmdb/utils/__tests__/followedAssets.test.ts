import { describe, expect, it } from 'vitest';
import {
  addFollowedAsset,
  normalizeFollowedAssetsConfig,
} from '@/app/cmdb/utils/followedAssets';

const INST_UUID = '63e4a531-b6bb-43cc-9eae-8eb8a09f795e';

describe('followed assets UUID contract', () => {
  it('reads a UUID stored in the legacy inst_id alias', () => {
    const normalized = normalizeFollowedAssetsConfig({
      items: [{ model_id: 'host', inst_id: INST_UUID } as never],
    });

    expect(normalized.items[0].inst_uuid).toBe(INST_UUID);
    expect(normalized.items[0]).not.toHaveProperty('inst_id');
  });

  it('new writes contain only inst_uuid', () => {
    const config = addFollowedAsset(
      { items: [] },
      { model_id: 'host', inst_uuid: INST_UUID },
      '2026-01-01T00:00:00Z'
    );

    expect(config.items).toEqual([
      { model_id: 'host', inst_uuid: INST_UUID, followed_at: '2026-01-01T00:00:00Z' },
    ]);
    expect(config.items[0]).not.toHaveProperty('inst_id');
  });
});
