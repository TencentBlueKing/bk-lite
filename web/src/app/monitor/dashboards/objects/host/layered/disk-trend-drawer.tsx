'use client';

import React from 'react';
import { Drawer } from 'antd';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import { hostCategoryText } from './category-copy';
import ThinTimeSeries from './thin-time-series';
import { formatUnit } from './readings';
import styles from './layered.module.scss';

/** 与主机告警抽屉同宽，落在规格 420–480。 */
const DISK_TREND_DRAWER_WIDTH = 440;

export type DiskTrendKind = 'mount' | 'device';

const dashReading = (value: number | null | undefined, unit: 'percent' | 'byteps' | 'cps' | 'ms') => {
  if (value == null || !Number.isFinite(value)) return '—';
  return formatUnit(value, unit);
};

const legendReading = (value: number | null | undefined, unit: 'byteps' | 'cps' | 'ms' | 'percent') => {
  if (value == null || !Number.isFinite(value)) return undefined;
  return formatUnit(value, unit);
};

export default function DiskTrendDrawer({
  open,
  kind,
  row,
  loading,
  onClose
}: {
  open: boolean;
  kind: DiskTrendKind;
  row: EntityTableRow | null;
  loading: boolean;
  onClose: () => void;
}) {
  const { t } = useDashboardText();
  const emptyText = hostCategoryText(t, 'noData');
  const path = row?.labels.path || row?.labels.mount || '';
  const deviceName = row?.labels.name || row?.labels.device || '';
  const title = kind === 'mount'
    ? (path
      ? hostCategoryText(t, 'mountUsedNamed', { name: path })
      : hostCategoryText(t, 'mountUsed'))
    : (deviceName
      ? hostCategoryText(t, 'deviceTrendNamed', { name: deviceName })
      : hostCategoryText(t, 'deviceTrend'));

  return (
    <Drawer
      rootClassName={styles.diskTrendDrawer}
      title={(
        <span className="block truncate text-[14px] font-medium text-[var(--color-text-1)]" title={title}>
          {title}
        </span>
      )}
      placement="right"
      width={DISK_TREND_DRAWER_WIDTH}
      open={open}
      onClose={onClose}
      mask
      maskClosable
      keyboard
      destroyOnClose
      styles={{
        body: { padding: '12px 16px 16px', overflowY: 'auto' },
        wrapper: { maxWidth: 'min(440px, 100vw)' }
      }}
    >
      {kind === 'mount' ? (
        <MountTrend row={row} loading={loading} emptyText={emptyText} />
      ) : (
        <DeviceTrend row={row} loading={loading} emptyText={emptyText} />
      )}
    </Drawer>
  );
}

function MountTrend({
  row,
  loading,
  emptyText
}: {
  row: EntityTableRow | null;
  loading: boolean;
  emptyText: string;
}) {
  const { t } = useDashboardText();
  const points = row?.series.disk_used_percent || [];
  const used = row?.values.disk_used;
  const total = row?.values.disk_total;
  const usedText = used != null && Number.isFinite(used) ? formatUnit(used, 'bytes') : '—';
  const totalText = total != null && Number.isFinite(total) ? formatUnit(total, 'bytes') : '—';
  const deviceName = row?.labels.io_device || '';
  const percentText = dashReading(row?.values.disk_used_percent, 'percent');

  if (!row) {
    return <EmptyReading text={emptyText} />;
  }

  return (
    <div className={styles.diskTrendMount}>
      <div className="mb-3 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-3)]">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>
            {hostCategoryText(t, 'utilization')}
            <span className="ml-1 font-medium text-[var(--color-text-1)] tabular-nums">{percentText}</span>
          </span>
          <span className="tabular-nums text-[var(--color-text-1)]">
            {hostCategoryText(t, 'mountUsedOfTotal', { used: usedText, total: totalText })}
          </span>
        </div>
        <div>
          {hostCategoryText(t, 'relatedDevice')}
          <span className="ml-1 font-medium text-[var(--color-text-1)]">{deviceName || '—'}</span>
        </div>
      </div>
      <ThinTimeSeries
        title=""
        loading={loading && points.length === 0}
        unit="percent"
        emptyText={emptyText}
        data={pointsToChartData([{ points }])}
        legends={[{
          label: hostCategoryText(t, 'utilization'),
          color: HOST_PALETTE.orange
        }]}
      />
    </div>
  );
}

function DeviceTrend({
  row,
  loading,
  emptyText
}: {
  row: EntityTableRow | null;
  loading: boolean;
  emptyText: string;
}) {
  const { t } = useDashboardText();
  if (!row) {
    return <EmptyReading text={emptyText} />;
  }

  const charts: Array<{
    key: string;
    title: string;
    unit: 'byteps' | 'cps' | 'ms';
    fallback: Array<{ key: string; label: string; color: string }>;
  }> = [
    {
      key: 'throughput',
      title: hostCategoryText(t, 'readWriteThroughput'),
      unit: 'byteps',
      fallback: [
        { key: 'diskio_read_bytes_rate', label: hostCategoryText(t, 'read'), color: HOST_PALETTE.blue },
        { key: 'diskio_write_bytes_rate', label: hostCategoryText(t, 'write'), color: HOST_PALETTE.cyan }
      ]
    },
    {
      key: 'iops',
      title: hostCategoryText(t, 'readWriteIops'),
      unit: 'cps',
      fallback: [
        { key: 'diskio_reads_rate', label: hostCategoryText(t, 'readIops'), color: HOST_PALETTE.blue },
        { key: 'diskio_writes_rate', label: hostCategoryText(t, 'writeIops'), color: HOST_PALETTE.cyan }
      ]
    },
    {
      key: 'latency',
      title: hostCategoryText(t, 'rwLatency'),
      unit: 'ms',
      fallback: [
        { key: 'disk_read_latency', label: hostCategoryText(t, 'readLatency'), color: HOST_PALETTE.orange },
        { key: 'disk_write_latency', label: hostCategoryText(t, 'writeLatency'), color: HOST_PALETTE.blue }
      ]
    }
  ];

  return (
    <div className={`${styles.diskTrendDevice} flex flex-col gap-3`}>
      {charts.map((chart) => {
        const present = chart.fallback.filter((item) => (row.series[item.key] || []).length > 0);
        const legends = (present.length ? present : chart.fallback).map((item) => ({
          label: item.label,
          color: item.color,
          reading: legendReading(row.values[item.key], chart.unit)
        }));
        return (
          <ThinTimeSeries
            key={`${chart.key}-${row.key}`}
            title={chart.title}
            loading={loading && present.length === 0}
            unit={chart.unit}
            emptyText={emptyText}
            data={pointsToChartData(present.map((item) => ({ points: row.series[item.key] || [] })))}
            legends={legends}
          />
        );
      })}
    </div>
  );
}

function EmptyReading({ text }: { text: string }) {
  return (
    <div className="flex min-h-[160px] items-center justify-center text-[13px] text-[var(--color-text-3)]">
      {text}
    </div>
  );
}
