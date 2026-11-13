import { describe, expect, it } from 'vitest';
import { delegatedSceneBase, networkStatusTopologyApiPath } from '../displayDelegate';

describe('display scene delegate paths', () => {
  it('keeps share and authenticated paths, and switches a cast page to the cookie session', () => {
    expect(delegatedSceneBase(
      '/ops-analysis/view',
      undefined,
      'room3d',
      '/operation_analysis/api/scene_widgets/room3d',
    )).toBe('/operation_analysis/api/scene_widgets/room3d');
    expect(delegatedSceneBase(
      '/ops-analysis/share/session/abc',
      'abc',
      'room3d',
      '/operation_analysis/api/scene_widgets/room3d',
    )).toBe('/operation_analysis/api/dashboard_share/session/abc/room3d');
    expect(delegatedSceneBase(
      '/ops-analysis/display/view',
      undefined,
      'room3d',
      '/operation_analysis/api/scene_widgets/room3d',
    )).toBe('/operation_analysis/api/screen_display/current/room3d');
  });

  it('sends network status topology through the cast cookie only on the display page', () => {
    expect(networkStatusTopologyApiPath('/ops-analysis/view'))
      .toBe('/operation_analysis/api/scene_widgets/network_status_topology/');
    expect(networkStatusTopologyApiPath('/ops-analysis/share/session/abc'))
      .toBe('/operation_analysis/api/scene_widgets/network_status_topology/');
    expect(networkStatusTopologyApiPath('/ops-analysis/display/view'))
      .toBe('/operation_analysis/api/screen_display/current/network_status_topology/');
  });
});
