import type { SceneWidgetType } from './sceneWidget';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';

export interface SceneWidgetCapability {
  type: SceneWidgetType;
  selfFetch: boolean;
  surfaces: readonly OpsAnalysisWidgetSurface[];
  shareSupported: boolean;
  reportSupported: boolean;
}

export const SCENE_WIDGET_CAPABILITIES: Record<
  SceneWidgetType,
  SceneWidgetCapability
> = {
  networkStatusTopology: {
    type: 'networkStatusTopology',
    selfFetch: true,
    surfaces: ['dashboard', 'screen'],
    shareSupported: true,
    reportSupported: false,
  },
  application3D: {
    type: 'application3D',
    selfFetch: true,
    surfaces: ['screen'],
    shareSupported: true,
    reportSupported: false,
  },
};

export const getSceneWidgetCapability = (
  type?: string,
): SceneWidgetCapability | undefined =>
  type && Object.prototype.hasOwnProperty.call(SCENE_WIDGET_CAPABILITIES, type)
    ? SCENE_WIDGET_CAPABILITIES[type as SceneWidgetType]
    : undefined;

export const isSceneWidgetType = (type?: string): type is SceneWidgetType =>
  Boolean(getSceneWidgetCapability(type));

export const isSceneWidgetAllowedOnSurface = (
  type: string | undefined,
  surface: OpsAnalysisWidgetSurface,
): boolean => {
  const capability = getSceneWidgetCapability(type);
  if (!capability?.surfaces.includes(surface)) {
    return false;
  }
  if (surface === 'report' && !capability.reportSupported) {
    return false;
  }
  return true;
};

export const isSelfFetchSceneWidget = (type?: string): boolean =>
  getSceneWidgetCapability(type)?.selfFetch === true;
