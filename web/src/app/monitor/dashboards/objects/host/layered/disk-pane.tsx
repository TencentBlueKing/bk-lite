'use client';

import React, { useState } from 'react';
import { Tooltip } from 'antd';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { hostCategoryText } from './category-copy';
import {
  showDiskFsTypeColumn,
  type EntityTableRow
} from '../entity-series';
import LayeredEntityTable from './entity-table';
import { formatBytesPair, formatUnit, ROW_ACCENTS } from './readings';
import DiskTrendDrawer, { type DiskTrendKind } from './disk-trend-drawer';
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
  const showFsType = showDiskFsTypeColumn(mountRows);
  const showMountBody = loading || mountRows.length > 0;
  const showDeviceBody = loading || deviceRows.length > 0;
  const { t } = useDashboardText();
  const [trend, setTrend] = useState<{ kind: DiskTrendKind; key: string } | null>(null);
  const trendRow = trend == null
    ? null
    : (trend.kind === 'mount' ? mountRows : deviceRows).find((row) => row.key === trend.key) || null;

  const openTrend = (kind: DiskTrendKind, key: string) => {
    if (kind === 'mount') onSelectMount(key);
    else onSelectDevice(key);
    setTrend({ kind, key });
  };

  const trendColumn = (kind: DiskTrendKind, tip: string) => ({
    key: 'trend',
    title: '',
    width: 72,
    align: 'right' as const,
    fixed: 'right' as const,
    ellipsis: false,
    render: (row: EntityTableRow) => {
      const active = trend?.kind === kind && trend.key === row.key;
      return (
        <span className="flex justify-end">
          <Tooltip title={tip}>
            <button
              type="button"
              className={active ? `${styles.trendLink} ${styles.trendLinkOn}` : styles.trendLink}
              aria-pressed={active}
              onClick={(event) => {
                event.stopPropagation();
                openTrend(kind, row.key);
              }}
            >
              {hostCategoryText(t, 'viewTrend')}
            </button>
          </Tooltip>
        </span>
      );
    }
  });

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
              }] : []),
              trendColumn('mount', hostCategoryText(t, 'viewUsageTrend'))
            ]}
          />
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
              },
              trendColumn('device', hostCategoryText(t, 'viewDeviceTrend'))
            ]}
          />
        ) : (
          <div className={styles.note}>{hostCategoryText(t, 'noBlockDevices')}</div>
        )}
      </section>

      <DiskTrendDrawer
        open={trend != null}
        kind={trend?.kind || 'mount'}
        row={trendRow}
        loading={loading}
        onClose={() => setTrend(null)}
      />
    </div>
  );
}
