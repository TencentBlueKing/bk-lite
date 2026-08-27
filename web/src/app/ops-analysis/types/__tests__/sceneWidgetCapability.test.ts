import { describe, expect, it } from 'vitest';
import {
  getSceneWidgetCapability,
  isSceneWidgetAllowedOnSurface,
  isSceneWidgetType,
  isSelfFetchSceneWidget,
} from '../sceneWidgetCapability';

describe('scene widget capabilities', () => {
  it('registers application3D as a Screen-only self-fetch scene', () => {
    expect(getSceneWidgetCapability('application3D')).toEqual({
      type: 'application3D',
      selfFetch: true,
      surfaces: ['screen'],
      shareSupported: true,
      reportSupported: false,
    });
    expect(isSceneWidgetAllowedOnSurface('application3D', 'screen')).toBe(true);
    expect(isSceneWidgetAllowedOnSurface('application3D', 'dashboard')).toBe(false);
    expect(isSceneWidgetAllowedOnSurface('application3D', 'report')).toBe(false);
  });

  it('keeps networkStatusTopology available on Dashboard and Screen', () => {
    expect(isSceneWidgetAllowedOnSurface('networkStatusTopology', 'dashboard')).toBe(true);
    expect(isSceneWidgetAllowedOnSurface('networkStatusTopology', 'screen')).toBe(true);
    expect(isSceneWidgetAllowedOnSurface('networkStatusTopology', 'report')).toBe(false);
    expect(isSelfFetchSceneWidget('networkStatusTopology')).toBe(true);
    expect(getSceneWidgetCapability('networkStatusTopology')?.shareSupported).toBe(true);
    expect(getSceneWidgetCapability('networkStatusTopology')?.reportSupported).toBe(false);
  });

  it('rejects unknown scene types', () => {
    expect(isSceneWidgetType('room3D')).toBe(false);
    expect(isSelfFetchSceneWidget('unknown')).toBe(false);
  });
});
