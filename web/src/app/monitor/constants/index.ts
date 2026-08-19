import { LevelMap } from '@/app/monitor/types';
import {
  ALERT_LEVEL_COLORS,
  OBSERVABILITY_SERIES_COLORS,
} from '@/constants/observabilityChart';

const APPOINT_METRIC_IDS: string[] = [
  'cluster_pod_count',
  'cluster_node_count'
];

const OBJECT_DEFAULT_ICON: string = 'cc-default_默认';

const LEVEL_MAP: LevelMap = ALERT_LEVEL_COLORS;

// 折线图分类色板（AntV/G2）。recharts 版 lineChart 与 echarts 版
// echarts-line-chart 共用，按序列索引稳定分配，保证两类图表配色一致。
// 刻意剔除红/橙告警色系（#E86452 珊瑚红→粉、#FF9845 橙→青灰），把
// 红/橙留给严重度阈值（LEVEL_MAP critical/error/warning），避免数据
// 序列被误读成告警线、或填充与阈值色块互相糊掉。
const CHART_COLORS: string[] = [...OBSERVABILITY_SERIES_COLORS];

export { APPOINT_METRIC_IDS, LEVEL_MAP, OBJECT_DEFAULT_ICON, CHART_COLORS };
