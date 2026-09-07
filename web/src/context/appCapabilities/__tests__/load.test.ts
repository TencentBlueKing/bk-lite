import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadAuthorizedCapability, resetAppCapabilityCache } from '../load';

afterEach(() => {
  resetAppCapabilityCache();
});

describe('loadAuthorizedCapability', () => {
  it('does not load the module when the user is not authorized', async () => {
    const load = vi.fn(async () => ({ TrendChart: () => null }));

    await expect(
      loadAuthorizedCapability('alarm', { authorized: false, load })
    ).resolves.toBeNull();
    expect(load).not.toHaveBeenCalled();
  });

  it('loads once and reuses the in-flight result', async () => {
    const load = vi.fn(async () => ({ TrendChart: () => null }));

    const [first, second] = await Promise.all([
      loadAuthorizedCapability('alarm', { authorized: true, load }),
      loadAuthorizedCapability('alarm', { authorized: true, load }),
    ]);

    expect(load).toHaveBeenCalledTimes(1);
    expect(first).toEqual(second);
  });

  it('returns null when the loader fails', async () => {
    await expect(
      loadAuthorizedCapability('alarm', {
        authorized: true,
        load: async () => {
          throw new Error('missing chunk');
        },
      })
    ).resolves.toBeNull();
  });
});
