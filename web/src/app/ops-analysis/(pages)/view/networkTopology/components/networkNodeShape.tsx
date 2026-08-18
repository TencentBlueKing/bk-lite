import React from 'react';
import { Tag } from 'antd';
import type {
  NetworkMetricRuntime,
  NetworkNodeRuntime,
  NetworkTopologyMetric,
  NetworkTopologyNode,
} from '@/app/ops-analysis/types/networkTopology';
import { useTranslation } from '@/utils/i18n';
import { resolveNodeOuterColor, NODE_UNFALLBACK_COLOR } from '../utils/nodeStatus';
import { formatNetworkMetricValue } from '../utils/metricValueFormat';

export interface NetworkNodeShapeProps {
  node: NetworkTopologyNode;
  nodeRuntime?: NetworkNodeRuntime;
  selected?: boolean;
  /** 节点叠加 invalid 视觉(WeOps 节点失效 / 采集失效)。 */
  invalid?: boolean;
  invalidReason?: string;
}

/**
 * X6 ReactShape 节点渲染(design.md §7.2 / §7.7):
 * - 沿用 v0 节点卡片 DOM
 * - 外层颜色 = 用户配置阈值命中,通过 inline style 传入(不预设)
 * - 选中态加 border + beacon 颜色 = 当前状态
 *
 * 由父级 (NetworkCanvas) 通过 @antv/x6-react-shape 把此组件注册为 ReactShape。
 */
const formatMetricValue = (
  metric: NetworkTopologyMetric,
  runtime: NetworkMetricRuntime[] | undefined,
  t: (key: string) => string,
): string => {
  if (!runtime) return t('opsAnalysis.networkTopology.nodeShape.valueNoData');
  const hit = runtime.find(
    (item) =>
      item.metric_field === metric.metric_field &&
      item.result_table_id === metric.result_table_id,
  );
  if (!hit) return t('opsAnalysis.networkTopology.node.valueAfterSave');
  if (hit.status === 'error') return t('opsAnalysis.networkTopology.node.valueFailed');
  if (hit.value === null || hit.value === undefined) return t('opsAnalysis.networkTopology.node.valueNoData');
  return formatNetworkMetricValue(hit.value, hit.unit, {
    fallbackUnit: metric.unit,
  });
};

const NetworkNodeShape: React.FC<NetworkNodeShapeProps> = ({
  node,
  nodeRuntime,
  selected = false,
  invalid = false,
  invalidReason,
}) => {
  const { t } = useTranslation();
  const runtimeMetrics = nodeRuntime?.metrics ?? [];
  const outerColor =
    resolveNodeOuterColor(node.metrics, runtimeMetrics) ??
    (invalid ? '#dc2626' : NODE_UNFALLBACK_COLOR);

  const status =
    invalid
      ? 'critical'
      : (nodeRuntime?.status ?? 'unknown');

  const summary = nodeRuntime?.interface_summary;
  const summaryText = summary
    ? `${summary.up}/${summary.down}/${summary.unknown}`
    : 'unknown';

  return (
    <div
      data-testid="network-node-shape"
      data-status={status}
      className="w-[190px] min-h-[112px] select-none rounded-lg bg-[var(--color-bg-1,#ffffff)] p-2.5"
      style={{
        border: `1px solid ${
          selected ? 'var(--color-primary,#2f8fb0)' : 'var(--color-border-2,#cfdbe5)'
        }`,
        borderTop: `3px solid ${outerColor}`,
        boxShadow: selected
          ? '0 0 0 2px rgba(47,143,176,0.18), 0 16px 34px rgba(36,50,63,0.18)'
          : '0 12px 26px rgba(36,50,63,0.12)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="inline-grid h-8 w-8 place-items-center rounded-md bg-[var(--color-fill-2,#eef4f6)] text-[11px] font-bold text-[var(--color-text-2,#335364)]">
          {node.bk_obj_id.replace(/^bk_/, '').slice(0, 2).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-[var(--color-text-1,#1f2933)]">
            {node.bk_inst_name}
          </div>
          <div className="mt-0.5 text-[11px] text-[var(--color-text-3,#73808c)]">
            {node.ip_addr || node.bk_obj_id}
          </div>
        </div>
        <span
          aria-hidden
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: outerColor }}
        />
      </div>

      <div className="mt-2 flex items-center justify-between border-t border-[var(--color-border-1,#e4ebf0)] pt-1.5 text-[11px] text-[var(--color-text-2,#536270)]">
        <span>
          {t('opsAnalysis.networkTopology.nodeShape.interfaceLabel', undefined, { summary: summaryText })}
        </span>
        <span>{nodeRuntime?.error_code ?? t('opsAnalysis.networkTopology.nodeShape.normal')}</span>
      </div>

      {node.metrics.slice(0, 2).map((metric) => (
        <div
          key={`${metric.result_table_id}:${metric.metric_field}`}
          className="mt-1 flex justify-between text-[11px] text-[var(--color-text-2,#334250)]"
        >
          <span className="max-w-[130px] truncate">
            {metric.display_name || metric.metric_field}
          </span>
          <strong className="text-[var(--color-text-1,#192733)]">
            {formatMetricValue(metric, runtimeMetrics, t)}
          </strong>
        </div>
      ))}
      {node.metrics.length === 0 && (
        <div className="mt-1.5 text-[11px] text-[var(--color-text-3,#8a98a5)]">
          {t('opsAnalysis.networkTopology.nodeShape.noMetrics')}
        </div>
      )}

      {invalid && invalidReason && (
        <div className="mt-1.5">
          <Tag color="red">{invalidReason}</Tag>
        </div>
      )}
    </div>
  );
};

export default NetworkNodeShape;
