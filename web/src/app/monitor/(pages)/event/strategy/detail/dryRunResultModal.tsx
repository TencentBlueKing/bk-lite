'use client';
import { Alert, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import OperateModal from '@/components/operate-modal';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useLevelList } from '@/app/monitor/hooks';
import { formatMetricValue as formatScaledMetricValue } from '@/app/monitor/components/monitor-dashboard-widgets/runtime';
import type { MetricUnit } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import {
  DRY_RUN_VERDICT_I18N,
  formatDryRunDimensionLabel,
  formatDryRunNumber,
  resolveDryRunReason,
} from './strategyDetailUtils';

export interface DryRunItem {
  instance_id?: string;
  instance_name?: string;
  metric_instance_id?: string;
  verdict?: string;
  current_value?: number | null;
  baseline_value?: number | null;
  compared_value?: number | null;
  result_unit?: string;
  result_unit_display?: string;
  matched_threshold?: {
    method?: string;
    value?: number | string | null;
    level?: string;
  } | null;
  reason?: string;
  hit_count?: number;
  trigger_count?: number;
}

export interface DryRunResult {
  items?: DryRunItem[];
  truncated?: boolean;
  warnings?: string[];
}

interface DryRunResultModalProps {
  open: boolean;
  loading?: boolean;
  data: DryRunResult | null;
  dimensions?: Array<{ name?: string; description?: string }>;
  onClose: () => void;
  t: (key: string, fallback?: string) => string;
}

const VERDICT_ORDER = [
  'would_trigger',
  'would_recover',
  'hold',
  'ok',
  'no_data',
  'missing_baseline',
  'insufficient_samples',
];

const VERDICT_TAG_COLOR: Record<string, string> = {
  would_trigger: 'error',
  would_recover: 'success',
  hold: 'processing',
  ok: 'default',
  no_data: 'warning',
  missing_baseline: 'warning',
  insufficient_samples: 'warning',
};

const LEVEL_TAG_COLOR: Record<string, string> = {
  critical: 'error',
  error: 'orange',
  warning: 'warning',
};

const VERDICT_SUMMARY_COLOR: Record<string, string> = {
  would_trigger: 'var(--color-fail)',
  would_recover: 'var(--color-success)',
  hold: 'var(--color-primary)',
  ok: 'var(--color-text-2)',
  no_data: 'var(--color-warning)',
  missing_baseline: 'var(--color-warning)',
  insufficient_samples: 'var(--color-warning)',
};

const hasNumber = (value: unknown) => {
  if (value === null || value === undefined || value === '') return false;
  return Number.isFinite(Number(value));
};

const formatDryRunValue = (value: unknown, unit?: string) => {
  if (!hasNumber(value)) return '—';
  const number = Number(value);
  if (unit) {
    const formatted = formatScaledMetricValue(number, unit as MetricUnit);
    return [formatted.value, formatted.unit].filter(Boolean).join(' ');
  }
  return formatDryRunNumber(value);
};

const formatThresholdValue = (
  threshold: DryRunItem['matched_threshold'],
  unit?: string
) => {
  if (!threshold) return '—';
  const method = threshold.method || '';
  const value = formatDryRunValue(threshold.value, unit);
  if (!method && value === '—') return '—';
  return [method, value].filter(Boolean).join(' ');
};

const DryRunResultModal = ({
  open,
  loading = false,
  data,
  dimensions,
  onClose,
  t,
}: DryRunResultModalProps) => {
  const levelList = useLevelList();
  const translate = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const items = data?.items || [];
  const showBaseline = items.some((item) => hasNumber(item.baseline_value));
  const showReason = items.some((item) => Boolean(resolveDryRunReason(item)));
  const showLevel = items.some((item) => item.matched_threshold?.level);
  const verdictLabel = (verdict?: string) => {
    const i18nKey = verdict ? DRY_RUN_VERDICT_I18N[verdict] : '';
    return i18nKey ? t(i18nKey) : verdict || '—';
  };
  const levelLabel = (level?: string) => {
    if (!level) return '';
    return levelList.find((item) => item.value === level)?.label || level;
  };
  const verdictCounts = VERDICT_ORDER.flatMap((verdict) => {
    const count = items.filter((item) => item.verdict === verdict).length;
    return count > 0 ? [{ verdict, count }] : [];
  });

  const columns: ColumnsType<DryRunItem> = [
    {
      title: t('monitor.events.assetName', '资产名称'),
      dataIndex: 'instance_name',
      key: 'instance_name',
      ellipsis: true,
      render: (value, record) => {
        const text = value || record.instance_id || '—';
        return <EllipsisWithTooltip className="truncate" text={text} />;
      },
    },
    {
      title: t('monitor.events.dimension', '维度'),
      key: 'dimension',
      ellipsis: true,
      render: (_value, record) => {
        const text =
          formatDryRunDimensionLabel(record.metric_instance_id, dimensions) ||
          '—';
        return <EllipsisWithTooltip className="truncate" text={text} />;
      },
    },
    {
      title: translate('monitor.events.dryRunVerdict', '判定'),
      dataIndex: 'verdict',
      key: 'verdict',
      width: 96,
      render: (verdict: string) => (
        <Tag className="mr-0" color={VERDICT_TAG_COLOR[verdict] || 'default'}>
          {verdictLabel(verdict)}
        </Tag>
      ),
    },
    ...(showLevel
      ? [
          {
            title: t('monitor.events.level', '级别'),
            key: 'level',
            width: 88,
            render: (_value: unknown, record: DryRunItem) => {
              const level = record.matched_threshold?.level;
              if (!level) return '—';
              return (
                <Tag className="mr-0" color={LEVEL_TAG_COLOR[level] || 'default'}>
                  {levelLabel(level)}
                </Tag>
              );
            },
          } satisfies ColumnsType<DryRunItem>[number],
      ]
      : []),
    {
      title: t('monitor.events.dryRunCurrentValue', '当前值'),
      dataIndex: 'current_value',
      key: 'current_value',
      width: 112,
      render: (value, record) => formatDryRunValue(value, record.result_unit),
    },
    ...(showBaseline
      ? [
          {
            title: t('monitor.events.dryRunBaselineValue', '对照值'),
            dataIndex: 'baseline_value',
            key: 'baseline_value',
            width: 112,
            render: (value: unknown, record: DryRunItem) =>
              formatDryRunValue(value, record.result_unit),
          } satisfies ColumnsType<DryRunItem>[number],
      ]
      : []),
    {
      title: t('monitor.events.dryRunComparedValue', '比较值'),
      dataIndex: 'compared_value',
      key: 'compared_value',
      width: 112,
      render: (value, record) => formatDryRunValue(value, record.result_unit),
    },
    {
      title: t('monitor.events.dryRunMatchedThreshold', '命中阈值'),
      dataIndex: 'matched_threshold',
      key: 'matched_threshold',
      width: 120,
      render: (value, record) => formatThresholdValue(value, record.result_unit),
    },
    ...(showReason
      ? [
          {
            title: t('monitor.events.dryRunReason', '原因'),
            key: 'reason',
            ellipsis: true,
            render: (_value: unknown, record: DryRunItem) =>
              resolveDryRunReason(record) || '—',
          } satisfies ColumnsType<DryRunItem>[number],
      ]
      : []),
  ];

  return (
    <OperateModal
      title={
        <span className="inline-flex min-w-0 items-center gap-3">
          <span className="shrink-0">
            {translate('monitor.events.dryRunResult', '预检结果')}
          </span>
          {verdictCounts.length ? (
            <span className="inline-flex min-w-0 items-center gap-3 font-normal">
              <span className="h-3.5 w-px shrink-0 bg-[var(--color-border-1)]" />
              <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[13px] leading-none text-[var(--color-text-2)]">
                {verdictCounts.map((item) => {
                  const color =
                    VERDICT_SUMMARY_COLOR[item.verdict] || 'var(--color-text-3)';
                  return (
                    <span
                      key={item.verdict}
                      className="inline-flex items-center gap-1.5"
                    >
                      <span
                        className="h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: color }}
                      />
                      <span>{verdictLabel(item.verdict)}</span>
                      <span
                        className="font-medium tabular-nums"
                        style={{ color }}
                      >
                        {item.count}
                      </span>
                    </span>
                  );
                })}
              </span>
            </span>
          ) : null}
        </span>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={960}
    >
      {data?.truncated || (data?.warnings || []).length ? (
        <Alert
          className="mb-3"
          type="warning"
          showIcon
          message={
            (data?.warnings || []).join('；') ||
            translate('monitor.events.dryRunTruncated', '实例超过 200，已截断')
          }
        />
      ) : null}
      <Table
        className="w-full"
        size="small"
        tableLayout="fixed"
        rowKey={(row, index) =>
          `${row.metric_instance_id || row.instance_id || 'row'}-${index}`
        }
        loading={loading}
        pagination={false}
        scroll={items.length > 8 ? { y: 360 } : undefined}
        dataSource={items}
        columns={columns}
      />
    </OperateModal>
  );
};

export default DryRunResultModal;
