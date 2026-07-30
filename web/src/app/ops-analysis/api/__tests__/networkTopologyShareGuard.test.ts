import { describe, expect, it } from 'vitest';
import {
  NetworkTopologyShareEditBlockedError,
  NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS,
  isNetworkTopologyShareAccess,
  rejectNetworkTopologyEditApiInShareMode,
} from '../networkTopologyShareGuard';

describe('networkTopologyShareGuard', () => {
  it('treats shareMode / detail override / runtime as share access', () => {
    expect(isNetworkTopologyShareAccess()).toBe(false);
    expect(isNetworkTopologyShareAccess({ shareMode: true })).toBe(true);
    expect(isNetworkTopologyShareAccess({ shareDetailOverride: true })).toBe(true);
    expect(isNetworkTopologyShareAccess({ shareRuntime: true })).toBe(true);
  });

  it('allows edit APIs outside share access', () => {
    for (const api of NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS) {
      expect(() =>
        rejectNetworkTopologyEditApiInShareMode(false, api),
      ).not.toThrow();
    }
  });

  it('blocks edit APIs in share access with an explicit error', () => {
    for (const api of NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS) {
      try {
        rejectNetworkTopologyEditApiInShareMode(true, api);
        expect.unreachable(`expected ${api} to throw`);
      } catch (error) {
        expect(error).toBeInstanceOf(NetworkTopologyShareEditBlockedError);
        expect((error as NetworkTopologyShareEditBlockedError).api).toBe(api);
        expect((error as Error).message).toContain(api);
      }
    }
  });

  it('does not list runtime APIs as blocked edit APIs', () => {
    expect(NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS).not.toContain('getMetricValues');
    expect(NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS).not.toContain('getLinkRuntime');
    expect(NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS).not.toContain('getViewSets');
    expect(NETWORK_TOPOLOGY_SHARE_BLOCKED_EDIT_APIS).not.toContain(
      'getNetworkTopologyDetail',
    );
  });
});
