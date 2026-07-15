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
      style={{
        width: 190,
        minHeight: 112,
        padding: 10,
        background: '#fff',
        border: '1px solid ' + (selected ? '#2f8fb0' : '#cfdbe5'),
        borderTop: `3px solid ${outerColor}`,
        borderRadius: 8,
        boxShadow: selected
          ? '0 0 0 2px rgba(47,143,176,0.18), 0 16px 34px rgba(36,50,63,0.18)'
          : '0 12px 26px rgba(36,50,63,0.12)',
        userSelect: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-grid',
            placeItems: 'center',
            width: 32,
            height: 32,
            background: '#eef4f6',
            borderRadius: 6,
            color: '#335364',
            fontWeight: 700,
            fontSize: 11,
          }}
        >
          {node.bk_obj_id.replace(/^bk_/, '').slice(0, 2).toUpperCase()}
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontWeight: 650,
              fontSize: 13,
              color: '#1f2933',
            }}
          >
            {node.bk_inst_name}
          </div>
          <div
            style={{
              fontSize: 11,
              color: '#73808c',
              marginTop: 2,
            }}
          >
            {node.ip_addr || node.bk_obj_id}
          </div>
        </div>
        <span
          aria-hidden
          style={{
            width: 9,
            height: 9,
            borderRadius: 999,
            background: outerColor,
          }}
        />
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 8,
          paddingTop: 6,
          borderTop: '1px solid #e4ebf0',
          fontSize: 11,
          color: '#536270',
        }}
      >
        <span>
          {t('opsAnalysis.networkTopology.nodeShape.interfaceLabel', undefined, { summary: summaryText })}
        </span>
        <span>{nodeRuntime?.error_code ?? t('opsAnalysis.networkTopology.nodeShape.normal')}</span>
      </div>

      {node.metrics.slice(0, 2).map((metric) => (
        <div
          key={`${metric.result_table_id}:${metric.metric_field}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 11,
            color: '#334250',
            marginTop: 4,
          }}
        >
          <span
            style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: 130,
            }}
          >
            {metric.display_name || metric.metric_field}
          </span>
          <strong style={{ color: '#192733' }}>
            {formatMetricValue(metric, runtimeMetrics, t)}
          </strong>
        </div>
      ))}
      {node.metrics.length === 0 && (
        <div style={{ fontSize: 11, color: '#8a98a5', marginTop: 6 }}>
          {t('opsAnalysis.networkTopology.nodeShape.noMetrics')}
        </div>
      )}

      {invalid && invalidReason && (
        <div style={{ marginTop: 6 }}>
          <Tag color="red">{invalidReason}</Tag>
        </div>
      )}
    </div>
  );
};

export default NetworkNodeShape;
