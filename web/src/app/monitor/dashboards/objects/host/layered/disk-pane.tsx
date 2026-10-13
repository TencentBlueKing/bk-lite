'use client';

import React from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_PALETTE } from '../config';
import { hostCategoryText } from './category-copy';
import {
  pointsToChartData,
  rowHasSeries,
  showDiskFsTypeColumn,
  showDiskInodeColumn,
  type EntityTableRow
} from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatBytesPair, formatPercent, formatUnit, ROW_ACCENTS } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export const DISK_HOT_PERCENT = 80;

export const countHotMounts = (rows: EntityTableRow[]) => (
  rows.filter((row) => (row.values.disk_used_percent ?? -1) >= DISK_HOT_PERCENT).length
);

const LATENCY_KEYS = ['disk_read_latency', 'disk_write_latency'] as const;

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
  onSelectDevice,
  windowsHost = false
}: {
  mountRows: EntityTableRow[];
  deviceRows: EntityTableRow[];
  loading: boolean;
  errorText?: string;
  selectedMountKey: string;
  selectedDeviceKey: string;
  onSelectMount: (key: string) => void;
  onSelectDevice: (key: string) => void;
  windowsHost?: boolean;
}) {
  const selectedMount = mountRows.find((row) => row.key === selectedMountKey) || null;
  const selectedDevice = deviceRows.find((row) => row.key === selectedDeviceKey) || null;
  const path = selectedMount?.labels.path || selectedMount?.labels.mount || '';
  const deviceName = selectedDevice?.labels.name || selectedDevice?.labels.device || '';
  const used = selectedMount?.values.disk_used_percent;
  const usedValue = used == null || !Number.isFinite(used) ? null : used;
  const showUtil = (selectedDevice?.series.diskio_io_util || []).length > 0;
  const showLatency = rowHasSeries(selectedDevice || undefined, LATENCY_KEYS);
  const showInodes = showDiskInodeColumn(mountRows, windowsHost);
  const showFsType = showDiskFsTypeColumn(mountRows);
  const showMountBody = loading || mountRows.length > 0;
  const showDeviceBody = loading || deviceRows.length > 0;
  const { t } = useDashboardText();
  const latencyItems = [
    { key: 'disk_read_latency' as const, label: hostCategoryText(t, 'readLatency'), color: HOST_PALETTE.orange },
    { key: 'disk_write_latency' as const, label: hostCategoryText(t, 'writeLatency'), color: HOST_PALETTE.blue }
  ].filter((item) => (selectedDevice?.series[item.key] || []).length > 0);
  const followHint = hostCategoryText(t, 'chartFollowsSelection');
  const readTitle = deviceName
    ? hostCategoryText(t, 'deviceReadNamed', { name: deviceName })
    : hostCategoryText(t, 'deviceRead');
  const writeTitle = deviceName
    ? hostCategoryText(t, 'deviceWriteNamed', { name: deviceName })
    : hostCategoryText(t, 'deviceWrite');
  const ioTitle = deviceName
    ? hostCategoryText(t, 'ioUtilizationNamed', { name: deviceName })
    : hostCategoryText(t, 'ioUtilization');
  const latencyTitle = deviceName
    ? hostCategoryText(t, 'rwLatencyNamed', { name: deviceName })
    : hostCategoryText(t, 'rwLatency');
  const latencyReading = latencyItems.length
    ? latencyItems.map((item) => formatUnit(selectedDevice?.values[item.key] ?? null, 'ms')).join(' / ')
    : undefined;

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {errorText ? <div className={styles.note}>{errorText}</div> : null}

      <section className={styles.diskZone}>
        <div className={styles.sectionHead}>
          <div className={`${classic.sectionLabel} ${styles.sectionTitle} ${styles.diskZoneTitle}`}>
            {hostCategoryText(t, 'mounts')}
          </div>
          <div className={styles.hint}>{followHint}</div>
        </div>
        {showMountBody ? (
          <>
            <ThinTimeSeries
              key={`used-${selectedMount?.key || 'none'}`}
              title={path
                ? hostCategoryText(t, 'mountUsedNamed', { name: path })
                : hostCategoryText(t, 'mountUsed')}
              reading={formatPercent(usedValue)}
              loading={loading && !selectedMount}
              unit="percent"
              emptyText={selectedMount ? '暂无数据' : hostCategoryText(t, 'noMountPoints')}
              data={pointsToChartData([{ points: selectedMount?.series.disk_used_percent || [] }])}
              legends={[{ label: path || hostCategoryText(t, 'mountUsed'), color: HOST_PALETTE.orange }]}
            />
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
                  render: (row, index) => (
                    <span className={styles.nameCell}>
                      <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
                      {row.labels.path || '—'}
                    </span>
                  )
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
                ...(showInodes ? [{
                  key: 'disk_inodes_used_percent',
                  title: hostCategoryText(t, 'inodeUsage'),
                  unit: 'percent' as const,
                  emptyDash: true
                }] : []),
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
          <div className={styles.hint}>{followHint}</div>
        </div>
        {showDeviceBody ? (
          <>
            <div className={showLatency ? styles.chartGrid3 : styles.chartGrid2}>
              <ThinTimeSeries
                key={`read-${selectedDevice?.key || 'none'}`}
                title={readTitle}
                reading={selectedDevice
                  ? formatUnit(selectedDevice.values.diskio_read_bytes_rate ?? null, 'byteps')
                  : undefined}
                loading={loading && !selectedDevice}
                unit="byteps"
                emptyText={selectedDevice ? '暂无数据' : hostCategoryText(t, 'noBlockDevices')}
                data={pointsToChartData([{ points: selectedDevice?.series.diskio_read_bytes_rate || [] }])}
                legends={[{ label: hostCategoryText(t, 'deviceRead'), color: HOST_PALETTE.blue }]}
              />
              <ThinTimeSeries
                key={`write-${selectedDevice?.key || 'none'}`}
                title={writeTitle}
                reading={selectedDevice
                  ? formatUnit(selectedDevice.values.diskio_write_bytes_rate ?? null, 'byteps')
                  : undefined}
                loading={loading && !selectedDevice}
                unit="byteps"
                emptyText={selectedDevice ? '暂无数据' : hostCategoryText(t, 'noBlockDevices')}
                data={pointsToChartData([{ points: selectedDevice?.series.diskio_write_bytes_rate || [] }])}
                legends={[{ label: hostCategoryText(t, 'deviceWrite'), color: HOST_PALETTE.cyan }]}
              />
              {showLatency ? (
                <ThinTimeSeries
                  key={`latency-${selectedDevice?.key || 'none'}`}
                  title={latencyTitle}
                  reading={latencyReading}
                  loading={loading && !selectedDevice}
                  unit="ms"
                  data={pointsToChartData(latencyItems.map((item) => ({
                    points: selectedDevice?.series[item.key] || []
                  })))}
                  legends={latencyItems.map((item) => ({
                    label: item.label,
                    color: item.color
                  }))}
                />
              ) : null}
            </div>
            {showUtil ? (
              <ThinTimeSeries
                key={`util-${selectedDevice?.key || 'none'}`}
                title={ioTitle}
                reading={formatPercent(selectedDevice?.values.diskio_io_util ?? null)}
                loading={loading && !selectedDevice}
                unit="percent"
                data={pointsToChartData([{ points: selectedDevice?.series.diskio_io_util || [] }])}
                legends={[{ label: hostCategoryText(t, 'ioUtilization'), color: HOST_PALETTE.indigo }]}
              />
            ) : null}
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
