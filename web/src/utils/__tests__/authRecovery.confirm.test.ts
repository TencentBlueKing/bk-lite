import { describe, expect, it, vi } from 'vitest';

import {
  CONFIRM_AUTH_NETWORK_RETRY_DELAY_MS,
  confirmAuthStillValid,
  type RecoveredAuthUser,
} from '@/utils/authRecovery';

const user: RecoveredAuthUser = {
  id: '1',
  username: 'admin',
  token: 'fresh-token',
  locale: 'zh-Hans',
  timezone: 'Asia/Shanghai',
};

describe('confirmAuthStillValid', () => {
  it('returns the current user without retrying when the session is still valid', async () => {
    const checkAuth = vi.fn().mockResolvedValue(user);
    const waitForDelay = vi.fn();

    const result = await confirmAuthStillValid('1', checkAuth, CONFIRM_AUTH_NETWORK_RETRY_DELAY_MS, waitForDelay);

    expect(result).toEqual({ status: 'recovered', user });
    expect(checkAuth).toHaveBeenCalledTimes(1);
    expect(waitForDelay).not.toHaveBeenCalled();
  });

  it('does not retry a definitive unauthenticated probe', async () => {
    const checkAuth = vi.fn().mockResolvedValue(null);
    const waitForDelay = vi.fn();

    const result = await confirmAuthStillValid('1', checkAuth, 300, waitForDelay);

    expect(result).toEqual({ status: 'unavailable' });
    expect(checkAuth).toHaveBeenCalledTimes(1);
    expect(waitForDelay).not.toHaveBeenCalled();
  });

  it('retries once after a network error and then recovers', async () => {
    const checkAuth = vi.fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(user);
    const waitForDelay = vi.fn().mockResolvedValue(undefined);

    const result = await confirmAuthStillValid('1', checkAuth, 300, waitForDelay);

    expect(result).toEqual({ status: 'recovered', user });
    expect(checkAuth).toHaveBeenCalledTimes(2);
    expect(waitForDelay).toHaveBeenCalledTimes(1);
    expect(waitForDelay).toHaveBeenCalledWith(300);
  });

  it('stops after a second network error', async () => {
    const checkAuth = vi.fn().mockRejectedValue(new Error('network'));
    const waitForDelay = vi.fn().mockResolvedValue(undefined);

    const result = await confirmAuthStillValid('1', checkAuth, 300, waitForDelay);

    expect(result).toEqual({ status: 'unavailable' });
    expect(checkAuth).toHaveBeenCalledTimes(2);
    expect(waitForDelay).toHaveBeenCalledTimes(1);
  });

  it('reports an account change without retrying', async () => {
    const checkAuth = vi.fn().mockResolvedValue({ ...user, id: '2' });
    const waitForDelay = vi.fn();

    const result = await confirmAuthStillValid('1', checkAuth, 300, waitForDelay);

    expect(result).toEqual({ status: 'account-changed' });
    expect(checkAuth).toHaveBeenCalledTimes(1);
    expect(waitForDelay).not.toHaveBeenCalled();
  });

  it('does not probe when the expected user is unknown', async () => {
    const checkAuth = vi.fn();

    const result = await confirmAuthStillValid(null, checkAuth);

    expect(result).toEqual({ status: 'unavailable' });
    expect(checkAuth).not.toHaveBeenCalled();
  });

  it('does not probe after the confirmation has been aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const checkAuth = vi.fn();

    const result = await confirmAuthStillValid('1', checkAuth, 300, vi.fn(), controller.signal);

    expect(result).toEqual({ status: 'unavailable' });
    expect(checkAuth).not.toHaveBeenCalled();
  });
});
