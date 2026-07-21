/**
 * 节点外层颜色聚合(design.md §2.5, §7.7, §9.2)。
 *
 * 完全由用户配置的阈值决定颜色,**没有任何预设严重级**。
 *
 * 节点聚合规则:
 * 1. 每个指标根据其 `thresholds` 找最深命中(null 值/null runtime/NaN/runtime 错误均不参与)
 * 2. 在所有命中里按"命中位置(level)降序"排序,平局按指标 `sort_order` 升序
 * 3. 最深命中指标的颜色 = 节点外层颜色
 * 4. 全 null -> 返回 null(由上层渲染为 unknown 灰色)
 */

import type {
  NetworkTopologyMetric,
  NetworkMetricRuntime,
} from '@/app/ops-analysis/types/networkTopology';
import {
  pickDeepestThresholdHit,
  type SimpleThreshold,
} from './thresholdUtils';

/** 节点未知/无数据时的渲染兜底色(与 v0 默认一致,见 design.md §9.2)。 */
export const NODE_UNFALLBACK_COLOR = '#64748b';

/**
 * 单个指标根据其当前 runtime 值,找到命中阈值的最深位置。
 * 输入:
 * - metric: 节点上保存的指标定义(必须包含 `thresholds`)
 * - runtime: WeOps batch 接口返回的对应运行时值,可为 undefined
 * 返回:
 * - 命中 -> `{ level, color }`
 * - 无阈值 / 无 runtime / runtime 值无效 / runtime.status=error -> `null`
 */
/** 节点指标命中的最小输入(测试与外部代码都可能传入简化版)。 */
export interface MinimalNodeMetricLike {
  metric_field?: string;
  result_table_id?: string;
  thresholds?: ReadonlyArray<SimpleThreshold>;
}

export function resolveActiveThreshold(
  metric: NetworkTopologyMetric | MinimalNodeMetricLike | null | undefined,
  runtime: NetworkMetricRuntime | undefined,
): { level: number; color: string } | null {
  if (!metric || !Array.isArray(metric.thresholds) || metric.thresholds.length === 0) {
    return null;
  }
  if (!runtime) return null;

  // 要求 runtime 既匹配 metric_field 也匹配 result_table_id,避免跨模板的指标串台。
  if (
    typeof metric.metric_field === 'string' &&
    runtime.metric_field !== metric.metric_field
  ) {
    return null;
  }
  if (
    typeof metric.result_table_id === 'string' &&
    runtime.result_table_id !== metric.result_table_id
  ) {
    return null;
  }
  if (runtime.status === 'error') return null;

  const raw = runtime.value;
  if (raw === null || raw === undefined) return null;
  const numericValue = Number(raw);
  if (!Number.isFinite(numericValue)) return null;

  return pickDeepestThresholdHit(metric.thresholds as SimpleThreshold[], numericValue);
}

/**
 * 聚合节点所有指标的命中,得到节点外层颜色。
 * 返回 `null` 表示:
 * - 节点没有任何指标;或
 * - 所有指标都拿不到 runtime 值 / 全部 error
 * 渲染端应把 `null` 显示为 `NODE_UNFALLBACK_COLOR`。
 */
export function resolveNodeOuterColor(
  metrics: ReadonlyArray<NetworkTopologyMetric>,
  runtimeMetrics: ReadonlyArray<NetworkMetricRuntime>,
): string | null {
  if (!Array.isArray(metrics) || metrics.length === 0) return null;

  interface Candidate {
    sortOrder: number;
    level: number;
    color: string;
  }
  const candidates: Candidate[] = [];

  for (let i = 0; i < metrics.length; i += 1) {
    const metric = metrics[i];
    const matchingRuntimeMetrics = runtimeMetrics.filter(
      (item) =>
        item.metric_field === metric.metric_field &&
        item.result_table_id === metric.result_table_id,
    );
    const runtime =
      matchingRuntimeMetrics.find((item) => item.sort_order === metric.sort_order) ??
      (matchingRuntimeMetrics.length === 1 ? matchingRuntimeMetrics[0] : undefined);
    const hit = resolveActiveThreshold(metric, runtime);
    if (hit === null) continue;
    candidates.push({
      sortOrder: metric.sort_order ?? i,
      level: hit.level,
      color: hit.color,
    });
  }

  if (candidates.length === 0) return null;

  candidates.sort((a, b) => {
    // 最深命中(level 越大)排前
    if (b.level !== a.level) return b.level - a.level;
    // 平局:sort_order 小的先排(用户先配的)
    return a.sortOrder - b.sortOrder;
  });

  return candidates[0].color;
}
