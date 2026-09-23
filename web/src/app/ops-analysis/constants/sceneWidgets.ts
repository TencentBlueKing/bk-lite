import type { SceneWidgetType } from '@/app/ops-analysis/types/sceneWidget';

export interface SceneWidgetDefinition {
  type: SceneWidgetType;
  nameKey: string;
  descriptionKey: string;
  category: 'cmdb';
  categoryNameKey: string;
  defaultWidth: number;
  defaultHeight: number;
}

export const SCENE_WIDGETS: SceneWidgetDefinition[] = [
  {
    type: 'networkStatusTopology',
    nameKey: 'dashboard.networkStatusTopology',
    descriptionKey: 'dashboard.networkStatusTopologyDesc',
    category: 'cmdb',
    categoryNameKey: 'dashboard.sceneCategoryCmdb',
    defaultWidth: 4,
    defaultHeight: 3,
  },
  {
    type: 'application3D',
    nameKey: 'dashboard.application3D',
    descriptionKey: 'dashboard.application3DDesc',
    category: 'cmdb',
    categoryNameKey: 'dashboard.sceneCategoryCmdb',
    defaultWidth: 4,
    defaultHeight: 3,
  },
  {
    type: 'relatedTopology',
    nameKey: 'dashboard.relatedTopology',
    descriptionKey: 'dashboard.relatedTopologyDesc',
    category: 'cmdb',
    categoryNameKey: 'dashboard.sceneCategoryCmdb',
    defaultWidth: 4,
    defaultHeight: 3,
  },
  {
    type: 'room3D',
    nameKey: 'dashboard.room3D',
    descriptionKey: 'dashboard.room3DDesc',
    category: 'cmdb',
    categoryNameKey: 'dashboard.sceneCategoryCmdb',
    defaultWidth: 4,
    defaultHeight: 3,
  },
];
