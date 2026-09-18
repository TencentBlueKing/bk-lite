'use client';
import { Alert, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import OperateModal from '@/components/operate-modal';
import {
  DRY_RUN_VERDICT_I18N,
  formatDryRunNumber,
  formatDryRunThreshold,
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
  onClose: () => void;
  t: (key: string, fallback?: string) => string;
}

const DryRunResultModal = ({
  open,
  loading = false,
  data,
  onClose,
  t,
}: DryRunResultModalProps) => {
  const translate = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const items = data?.items || [];
  const columns: ColumnsType<DryRunItem> = [
    {
      title: t('monitor.events.assetName', '资产名称'),
      dataIndex: 'instance_name',
      key: 'instance_name',
      ellipsis: true,
      render: (value, record) => value || record.instance_id || '—',
    },
    {
      title: t('monitor.events.level', '级别'),
      dataIndex: 'verdict',
      key: 'verdict',
      width: 120,
      render: (verdict: string) => {
        const i18nKey = DRY_RUN_VERDICT_I18N[verdict];
        return i18nKey ? t(i18nKey) : verdict || '—';
      },
    },
    {
      title: t('monitor.events.dryRunCurrentValue', '当前值'),
      dataIndex: 'current_value',
      key: 'current_value',
      width: 110,
      render: (value) => formatDryRunNumber(value),
    },
    {
      title: t('monitor.events.dryRunBaselineValue', '对照值'),
      dataIndex: 'baseline_value',
      key: 'baseline_value',
      width: 110,
      render: (value) => formatDryRunNumber(value),
    },
    {
      title: t('monitor.events.dryRunComparedValue', '比较值'),
      dataIndex: 'compared_value',
      key: 'compared_value',
      width: 110,
      render: (value, record) => {
        const formatted = formatDryRunNumber(value);
        if (formatted === '—') return formatted;
        return record.result_unit
          ? `${formatted} ${record.result_unit}`
          : formatted;
      },
    },
    {
      title: t('monitor.events.dryRunMatchedThreshold', '命中阈值'),
      dataIndex: 'matched_threshold',
      key: 'matched_threshold',
      width: 140,
      render: (value) => formatDryRunThreshold(value),
    },
    {
      title: t('monitor.events.dryRunReason', '原因'),
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
      render: (_value, record) => resolveDryRunReason(record) || '—',
    },
  ];

  return (
    <OperateModal
      title={translate('monitor.events.dryRunResult', '试跑结果')}
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
        size="small"
        rowKey={(row, index) =>
          `${row.metric_instance_id || row.instance_id || 'row'}-${index}`
        }
        loading={loading}
        pagination={false}
        scroll={{ y: 360 }}
        dataSource={items}
        columns={columns}
      />
    </OperateModal>
  );
};

export default DryRunResultModal;
