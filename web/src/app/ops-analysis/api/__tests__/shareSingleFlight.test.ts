import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  prepareShareToken,
  resetShareSingleFlightForTests,
  shareSingleFlight,
} from '@/app/ops-analysis/api/dashboardShare';
import { activateScreenDisplay } from '@/app/ops-analysis/api/screenDisplay';
import { isDashboardShareEntryPath } from '@/app/routeScope';

afterEach(() => {
  resetShareSingleFlightForTests();
  vi.unstubAllGlobals();
});

describe('share entry path', () => {
  it('keeps the token page on the page and leaves continue and session behind login', () => {
    expect(isDashboardShareEntryPath('/ops-analysis/share/signed.token')).toBe(true);
    expect(isDashboardShareEntryPath('/ops-analysis/share/continue')).toBe(false);
    expect(isDashboardShareEntryPath('/ops-analysis/share/session/abc')).toBe(false);
  });
});

describe('share single flight', () => {
  it('collapses overlapping prepares of the same token into one request', async () => {
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(async () => {
      calls += 1;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return {
        ok: true,
        json: async () => ({ result: true, data: { state: 'state-1' } }),
      };
    }));

    const [first, second] = await Promise.all([
      prepareShareToken('token-a'),
      prepareShareToken('token-a'),
    ]);

    expect(calls).toBe(1);
    expect(first).toEqual({ state: 'state-1' });
    expect(second).toEqual(first);
  });

  it('reuses a finished prepare for the remount window, then calls again', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ result: true, data: { state: 'state-a' } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ result: true, data: { state: 'state-b' } }),
      });
    vi.stubGlobal('fetch', fetchMock);

    await expect(prepareShareToken('token-c')).resolves.toEqual({ state: 'state-a' });
    await expect(prepareShareToken('token-c')).resolves.toEqual({ state: 'state-a' });
    await vi.advanceTimersByTimeAsync(2000);
    await expect(prepareShareToken('token-c')).resolves.toEqual({ state: 'state-b' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it('does not reuse a failed prepare, so a later retry reaches the server', async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ result: true, data: { state: 'state-2' } }),
      });
    vi.stubGlobal('fetch', fetchMock);

    await expect(prepareShareToken('token-b')).rejects.toThrow('network');
    await expect(prepareShareToken('token-b')).resolves.toEqual({ state: 'state-2' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('collapses overlapping display activations into one request', async () => {
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(async () => {
      calls += 1;
      await new Promise((resolve) => setTimeout(resolve, 10));
      return {
        ok: true,
        json: async () => ({ result: true, data: { ok: true } }),
      };
    }));
    const [first, second] = await Promise.all([
      activateScreenDisplay('display-token'),
      activateScreenDisplay('display-token'),
    ]);
    expect(calls).toBe(1);
    expect(second).toEqual(first);
  });

  it('returns the in-flight exchange result to the second caller and drops a failure', async () => {
    let calls = 0;
    const first = shareSingleFlight('exchange:state-1', async () => {
      calls += 1;
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { session_id: 's1' };
    });
    const second = shareSingleFlight('exchange:state-1', async () => {
      calls += 1;
      return { session_id: 'other' };
    });
    await expect(Promise.all([first, second])).resolves.toEqual([
      { session_id: 's1' },
      { session_id: 's1' },
    ]);
    expect(calls).toBe(1);

    await expect(shareSingleFlight('exchange:state-2', async () => {
      throw new Error('gone');
    })).rejects.toThrow('gone');
    await expect(shareSingleFlight('exchange:state-2', async () => 'retried')).resolves.toBe('retried');
  });
});
