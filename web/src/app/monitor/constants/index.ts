import { LevelMap } from '@/app/monitor/types';

const APPOINT_METRIC_IDS: string[] = [
  'cluster_pod_count',
  'cluster_node_count'
];

const OBJECT_DEFAULT_ICON: string = 'cc-default_默认';

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42'
};

// 折线图分类色板（AntV/G2）。recharts 版 lineChart 与 echarts 版
// echarts-line-chart 共用，按序列索引稳定分配，保证两类图表配色一致。
const CHART_COLORS: string[] = [
  '#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452',
  '#6DC8EC', '#945FB9', '#FF9845', '#1E9493'
];

export { APPOINT_METRIC_IDS, LEVEL_MAP, OBJECT_DEFAULT_ICON, CHART_COLORS };
