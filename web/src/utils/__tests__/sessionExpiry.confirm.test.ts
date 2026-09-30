import { afterEach, describe, expect, it } from 'vitest';

import {
  SESSION_EXPIRED_EVENT,
  emitSessionExpired,
  isSessionExpiredState,
  isSessionExpiryConfirming,
  latchSessionExpired,
  resetSessionExpiredState,
} from '@/utils/sessionExpiry';

afterEach(() => {
  resetSessionExpiredState();
  window.history.pushState({}, '', '/');
});

describe('session expiry confirmation', () => {
  it('coalesces 401s until the probe confirms the session is expired', () => {
    const reasons: string[] = [];
    const onExpired = (event: Event) => {
      reasons.push((event as CustomEvent<{ reason?: string }>).detail?.reason ?? '');
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);

    emitSessionExpired({ reason: 'first-401', status: 401 });
    emitSessionExpired({ reason: 'second-401', status: 401 });

    expect(reasons).toEqual(['first-401']);
    expect(isSessionExpiryConfirming()).toBe(true);
    expect(isSessionExpiredState()).toBe(false);

    latchSessionExpired();
    emitSessionExpired({ reason: 'third-401', status: 401 });

    expect(reasons).toEqual(['first-401']);
    expect(isSessionExpiryConfirming()).toBe(false);
    expect(isSessionExpiredState()).toBe(true);

    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  });

  it('allows another confirmation after the session is restored', () => {
    let events = 0;
    const onExpired = () => {
      events += 1;
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);

    emitSessionExpired({ reason: 'first-401', status: 401 });
    resetSessionExpiredState();
    emitSessionExpired({ reason: 'later-401', status: 401 });

    expect(events).toBe(2);
    expect(isSessionExpiryConfirming()).toBe(true);
    expect(isSessionExpiredState()).toBe(false);

    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  });

  it('does not start a confirmation on a dashboard render route', () => {
    window.history.pushState({}, '', '/ops-analysis/render/execution/7');
    let events = 0;
    const onExpired = () => {
      events += 1;
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);

    emitSessionExpired({ reason: 'render-401', status: 401 });

    expect(events).toBe(0);
    expect(isSessionExpiryConfirming()).toBe(false);
    expect(isSessionExpiredState()).toBe(false);

    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  });
});
