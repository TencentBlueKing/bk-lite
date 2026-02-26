import { LevelMap } from '@/app/monitor/types';

const APPOINT_METRIC_IDS: string[] = [
  'cluster_pod_count',
  'cluster_node_count'
];

const DERIVATIVE_OBJECTS = [
  'Docker Container',
  'ESXI',
  'VM',
  'DataStorage',
  'Pod',
  'Node',
  'CVM',
  'SangforSCPHost'
];

const OBJECT_DEFAULT_ICON: string = 'ziyuan';

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42'
};

export {
  APPOINT_METRIC_IDS,
  LEVEL_MAP,
  DERIVATIVE_OBJECTS,
  OBJECT_DEFAULT_ICON
};
