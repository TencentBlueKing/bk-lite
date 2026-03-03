import { LevelMap } from '@/app/monitor/types';

const APPOINT_METRIC_IDS: string[] = [
  'cluster_pod_count',
  'cluster_node_count'
];

const OBJECT_DEFAULT_ICON: string = 'ziyuan';

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42'
};

export { APPOINT_METRIC_IDS, LEVEL_MAP, OBJECT_DEFAULT_ICON };
