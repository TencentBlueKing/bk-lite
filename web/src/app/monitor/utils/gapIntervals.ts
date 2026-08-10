// 兼容旧调用路径；断点算法的唯一实现位于 monitor-chart-runtime。
export {
  GAP_INTERVAL_AREA_STYLE,
  GAP_INTERVAL_BOUNDARY_STYLE,
  attachGapIntervals,
  buildGapDetectionParams,
  deriveFinitePointGapIntervals,
  deriveVisibleGapIntervalsFromChartData,
  expandGapIntervalsToChartPoints,
  getChartDataWithGapBreaks,
  getRenderedGapIntervals,
  mergeGapIntervalsForDisplay,
  normalizeGapIntervals,
} from '@/app/monitor/components/monitor-chart-runtime/gap-intervals';
