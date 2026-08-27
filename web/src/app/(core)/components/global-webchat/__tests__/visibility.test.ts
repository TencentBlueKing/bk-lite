import { describe, expect, it } from 'vitest';

import {
  hasOpsPilotClientAccess,
  isGlobalWebchatExcludedPath,
  resolveStoredSelection,
  shouldKeepGlobalWebchat,
  shouldMountGlobalWebchat,
} from '../visibility';

describe('global webchat visibility', () => {
  it('requires OpsPilot in the user client list', () => {
    expect(hasOpsPilotClientAccess([{ name: 'monitor' }])).toBe(false);
    expect(hasOpsPilotClientAccess([{ name: 'opspilot' }])).toBe(true);
  });

  it('hides only on login and permission error routes', () => {
    expect(isGlobalWebchatExcludedPath('/auth/signin')).toBe(true);
    expect(isGlobalWebchatExcludedPath('/no-permission')).toBe(true);
    expect(isGlobalWebchatExcludedPath('/opspilot/studio/chat')).toBe(false);
    expect(isGlobalWebchatExcludedPath('/ops-analysis/share/abc')).toBe(false);
    expect(isGlobalWebchatExcludedPath('/ops-analysis/render/execution/7')).toBe(false);
    expect(isGlobalWebchatExcludedPath('/monitor/dashboard')).toBe(false);
  });

  it('waits for client loading and OpsPilot access before mounting', () => {
    expect(
      shouldMountGlobalWebchat({
        authenticated: true,
        clientLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/cmdb',
      }),
    ).toBe(false);
    expect(
      shouldMountGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        hasOpsPilotAccess: false,
        pathname: '/cmdb',
      }),
    ).toBe(false);
    expect(
      shouldMountGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        userInfoLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/cmdb',
      }),
    ).toBe(false);
    expect(
      shouldMountGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        hasOpsPilotAccess: true,
        pathname: '/cmdb',
      }),
    ).toBe(true);
  });

  it('keeps the widget mounted while client lists briefly reload', () => {
    expect(
      shouldKeepGlobalWebchat({
        authenticated: true,
        clientLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/opspilot/skill',
        alreadyMounted: true,
      }),
    ).toBe(true);
    expect(
      shouldKeepGlobalWebchat({
        authenticated: true,
        clientLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/opspilot/skill',
        alreadyMounted: false,
      }),
    ).toBe(false);
    expect(
      shouldKeepGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        hasOpsPilotAccess: false,
        pathname: '/opspilot/skill',
        alreadyMounted: true,
      }),
    ).toBe(false);
    expect(
      shouldKeepGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        userInfoLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/opspilot/skill',
        alreadyMounted: false,
      }),
    ).toBe(false);
    expect(
      shouldKeepGlobalWebchat({
        authenticated: true,
        clientLoading: false,
        userInfoLoading: true,
        hasOpsPilotAccess: true,
        pathname: '/opspilot/skill',
        alreadyMounted: true,
      }),
    ).toBe(true);
  });

  it('falls back to the first app when the stored id is gone after a team switch', () => {
    const apps = [
      { id: 'a' },
      { id: 'b' },
    ];
    expect(resolveStoredSelection(apps, 'b')?.id).toBe('b');
    expect(resolveStoredSelection(apps, 'missing')?.id).toBe('a');
  });
});
