'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_PALETTE } from '../config';
import { hostCategoryText } from './category-copy';
import {
  pointsToChartData,
  showDiskFsTypeColumn,
  type EntityTableRow
} from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatBytesPair, formatUnit, ROW_ACCENTS } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export const DISK_HOT_PERCENT = 80;

export const countHotMounts = (rows: EntityTableRow[]) => (
  rows.filter((row) => (row.values.disk_used_percent ?? -1) >= DISK_HOT_PERCENT).length
);

const formatLatencyPair = (row: EntityTableRow) => {
  const read = row.values.disk_read_latency;
  const write = row.values.disk_write_latency;
  const hasRead = read != null && Number.isFinite(read);
  const hasWrite = write != null && Number.isFinite(write);
  if (!hasRead && !hasWrite) return '—';
  return `${hasRead ? formatUnit(read, 'ms') : '—'} / ${hasWrite ? formatUnit(write, 'ms') : '—'}`;
};

const relatedMounts = (mountRows: EntityTableRow[], deviceName: string) => (
  mountRows
    .filter((row) => row.labels.io_device === deviceName)
    .map((row) => row.labels.path || row.labels.mount || '')
    .filter(Boolean)
);

export default function DiskPane({
  mountRows,
  deviceRows,
  loading,
  errorText,
  selectedMountKey,
  selectedDeviceKey,
  onSelectMount,
  onSelectDevice
}: {
  mountRows: EntityTableRow[];
  deviceRows: EntityTableRow[];
  loading: boolean;
  errorText?: string;
  selectedMountKey: string;
  selectedDeviceKey: string;
  onSelectMount: (key: string) => void;
  onSelectDevice: (key: string) => void;
  /** 调用方仍传入。inode 列始终展示，缺采集显示 —，不再按系统藏列。 */
  windowsHost?: boolean;
}) {
  const selectedMount = mountRows.find((row) => row.key === selectedMountKey) || null;
  const selectedDevice = deviceRows.find((row) => row.key === selectedDeviceKey) || null;
  const path = selectedMount?.labels.path || selectedMount?.labels.mount || '';
  const deviceName = selectedDevice?.labels.name || selectedDevice?.labels.device || '';
  const showFsType = showDiskFsTypeColumn(mountRows);
  const showMountBody = loading || mountRows.length > 0;
  const showDeviceBody = loading || deviceRows.length > 0;
  const { t } = useDashboardText();
  const emptyReading = hostCategoryText(t, 'noData');
  const latencyItems = [
    { key: 'disk_read_latency' as const, label: hostCategoryText(t, 'readLatency'), color: HOST_PALETTE.orange },
    { key: 'disk_write_latency' as const, label: hostCategoryText(t, 'writeLatency'), color: HOST_PALETTE.blue }
  ].filter((item) => (selectedDevice?.series[item.key] || []).length > 0);
  const followHint = hostCategoryText(t, 'chartFollowsSelection');
  const readTitle = deviceName
    ? hostCategoryText(t, 'readThroughputNamed', { name: deviceName })
    : hostCategoryText(t, 'readThroughput');
  const writeTitle = deviceName
    ? hostCategoryText(t, 'writeThroughputNamed', { name: deviceName })
    : hostCategoryText(t, 'writeThroughput');
  const iopsTitle = deviceName
    ? hostCategoryText(t, 'readWriteIopsNamed', { name: deviceName })
    : hostCategoryText(t, 'readWriteIops');
  const iopsItems = [
    {
      key: 'diskio_reads_rate' as const,
      label: hostCategoryText(t, 'readIops'),
      color: HOST_PALETTE.blue
    },
    {
      key: 'diskio_writes_rate' as const,
      label: hostCategoryText(t, 'writeIops'),
      color: HOST_PALETTE.cyan
    }
  ].filter((item) => (selectedDevice?.series[item.key] || []).length > 0);
  const latencyTitle = deviceName
    ? hostCategoryText(t, 'rwLatencyNamed', { name: deviceName })
    : hostCategoryText(t, 'rwLatency');

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {errorText ? <div className={styles.note}>{errorText}</div> : null}

      <section className={styles.diskZone}>
        <div className={styles.sectionHead}>
          <div className={`${classic.sectionLabel} ${styles.sectionTitle} ${styles.diskZoneTitle}`}>
            {hostCategoryText(t, 'mounts')}
          </div>
        </div>
        {showMountBody ? (
          <>
            <div className={styles.diskMountChart}>
              <ThinTimeSeries
                key={`used-${selectedMount?.key || 'none'}`}
                title={path
                  ? hostCategoryText(t, 'mountUsedNamed', { name: path })
                  : hostCategoryText(t, 'mountUsed')}
                loading={loading && !selectedMount}
                unit="percent"
                emptyText={emptyReading}
                data={pointsToChartData([{ points: selectedMount?.series.disk_used_percent || [] }])}
                legends={[{ label: path || hostCategoryText(t, 'mountUsed'), color: HOST_PALETTE.orange }]}
              />
              <div className={styles.hint}>{followHint}</div>
            </div>
            <LayeredEntityTable
              rows={mountRows}
              loading={loading}
              selectedKey={selectedMount?.key || ''}
              onSelect={onSelectMount}
              emptyText={hostCategoryText(t, 'noMountPoints')}
              columns={[
                {
                  key: 'path',
                  title: '挂载点',
                  labelKey: 'path',
                  width: 200,
                  render: (row, index) => {
                    const mountPath = row.labels.path || '';
                    return (
                      <span className={`${styles.nameCell} ${styles.nameCellTruncate}`}>
                        <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
                        <Tooltip title={mountPath || undefined}>
                          <span className={styles.pathEllipsis}>{mountPath || '—'}</span>
                        </Tooltip>
                      </span>
                    );
                  }
                },
                { key: 'disk_used_percent', title: '使用率', unit: 'percent', bar: true, emptyDash: true },
                {
                  key: 'disk_used',
                  title: '已用/总量',
                  render: (row) => formatBytesPair(row.values.disk_used, row.values.disk_total)
                },
                {
                  key: 'io_device',
                  title: hostCategoryText(t, 'relatedDevice'),
                  labelKey: 'io_device',
                  render: (row) => {
                    const name = row.labels.io_device || '';
                    if (!name) return '—';
                    const device = deviceRows.find((item) => (
                      item.labels.name === name || item.labels.device === name
                    ));
                    if (!device) return name;
                    const active = device.key === selectedDevice?.key;
                    return (
                      <button
                        type="button"
                        className={active ? `${styles.deviceLink} ${styles.deviceLinkOn}` : styles.deviceLink}
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectDevice(device.key);
                        }}
                      >
                        {name}
                      </button>
                    );
                  }
                },
                {
                  key: 'disk_inodes_used_percent',
                  title: hostCategoryText(t, 'inodeUsage'),
                  unit: 'percent' as const,
                  emptyDash: true
                },
                ...(showFsType ? [{
                  key: 'fstype',
                  title: hostCategoryText(t, 'filesystemType'),
                  labelKey: 'fstype',
                  emptyDash: true
                }] : [])
              ]}
            />
          </>
        ) : (
          <div className={styles.note}>{hostCategoryText(t, 'noMountPoints')}</div>
        )}
      </section>

      <section className={styles.diskZone}>
        <div className={styles.sectionHead}>
          <div className={`${classic.sectionLabel} ${styles.sectionTitle} ${styles.diskZoneTitle}`}>
            {hostCategoryText(t, 'blockDevices')}
          </div>
        </div>
        {showDeviceBody ? (
          <>
            <div className={styles.diskDeviceBlock}>
              <div className={styles.diskDeviceGrid}>
                <ThinTimeSeries
                  key={`read-${selectedDevice?.key || 'none'}`}
                  title={readTitle}
                  loading={loading && !selectedDevice}
                  unit="byteps"
                  emptyText={emptyReading}
                  data={pointsToChartData([{ points: selectedDevice?.series.diskio_read_bytes_rate || [] }])}
                  legends={[{ label: hostCategoryText(t, 'readThroughput'), color: HOST_PALETTE.blue }]}
                />
                <ThinTimeSeries
                  key={`write-${selectedDevice?.key || 'none'}`}
                  title={writeTitle}
                  loading={loading && !selectedDevice}
                  unit="byteps"
                  emptyText={emptyReading}
                  data={pointsToChartData([{ points: selectedDevice?.series.diskio_write_bytes_rate || [] }])}
                  legends={[{ label: hostCategoryText(t, 'writeThroughput'), color: HOST_PALETTE.cyan }]}
                />
                <ThinTimeSeries
                  key={`iops-${selectedDevice?.key || 'none'}`}
                  title={iopsTitle}
                  loading={loading && !selectedDevice}
                  unit="cps"
                  emptyText={emptyReading}
                  data={pointsToChartData(iopsItems.map((item) => ({
                    points: selectedDevice?.series[item.key] || []
                  })))}
                  legends={(iopsItems.length ? iopsItems : [
                    { key: 'diskio_reads_rate' as const, label: hostCategoryText(t, 'readIops'), color: HOST_PALETTE.blue },
                    { key: 'diskio_writes_rate' as const, label: hostCategoryText(t, 'writeIops'), color: HOST_PALETTE.cyan }
                  ]).map((item) => {
                    const value = selectedDevice?.values[item.key];
                    const reading = value != null && Number.isFinite(value) ? formatUnit(value, 'cps') : undefined;
                    return { label: item.label, color: item.color, reading };
                  })}
                />
                <ThinTimeSeries
                  key={`latency-${selectedDevice?.key || 'none'}`}
                  title={latencyTitle}
                  loading={loading && !selectedDevice}
                  unit="ms"
                  emptyText={emptyReading}
                  data={pointsToChartData(latencyItems.map((item) => ({
                    points: selectedDevice?.series[item.key] || []
                  })))}
                  legends={(latencyItems.length ? latencyItems : [
                    { label: hostCategoryText(t, 'readLatency'), color: HOST_PALETTE.orange },
                    { label: hostCategoryText(t, 'writeLatency'), color: HOST_PALETTE.blue }
                  ]).map((item) => ({
                    label: item.label,
                    color: item.color
                  }))}
                />
              </div>
              <div className={styles.hint}>{followHint}</div>
            </div>
            <LayeredEntityTable
              rows={deviceRows}
              loading={loading}
              selectedKey={selectedDevice?.key || ''}
              onSelect={onSelectDevice}
              emptyText={hostCategoryText(t, 'noBlockDevices')}
              columns={[
                {
                  key: 'name',
                  title: '设备',
                  labelKey: 'name',
                  render: (row, index) => (
                    <span className={styles.nameCell}>
                      <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
                      {row.labels.name || '—'}
                    </span>
                  )
                },
                { key: 'diskio_read_bytes_rate', title: '读', unit: 'byteps', emptyDash: true },
                { key: 'diskio_write_bytes_rate', title: '写', unit: 'byteps', emptyDash: true },
                { key: 'diskio_reads_rate', title: hostCategoryText(t, 'readIops'), unit: 'cps', emptyDash: true },
                { key: 'diskio_writes_rate', title: hostCategoryText(t, 'writeIops'), unit: 'cps', emptyDash: true },
                { key: 'diskio_io_util', title: hostCategoryText(t, 'ioUtilization'), unit: 'percent', emptyDash: true },
                {
                  key: 'latency',
                  title: hostCategoryText(t, 'latencyReadWrite'),
                  render: (row) => formatLatencyPair(row)
                },
                {
                  key: 'mounts',
                  title: '挂载点',
                  ellipsis: false,
                  render: (row) => {
                    const paths = relatedMounts(mountRows, row.labels.name || '');
                    if (!paths.length) return '—';
                    return (
                      <span className={styles.mountPaths}>
                        {paths.map((path) => (
                          <span key={path} className={styles.mountPath}>{path}</span>
                        ))}
                        <span className={styles.mountCount}>（{paths.length}）</span>
                      </span>
                    );
                  }
                }
              ]}
            />
          </>
        ) : (
          <div className={styles.note}>{hostCategoryText(t, 'noBlockDevices')}</div>
        )}
      </section>
    </div>
  );
}
