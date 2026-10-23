'use client';

import React, { useMemo, useState } from 'react';
import { Tooltip } from 'antd';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_SERIES_COLOR } from '../config';
import {
  latestPreferSignal,
  pointsToChartData,
  showDiskFsTypeColumn,
  showDiskInodeColumn,
  type EntityTableRow
} from '../entity-series';
import { hostCategoryText, type HostCategoryCopyKey } from './category-copy';
import classic from '../index.module.scss';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import TableCsvExportButton from './table-csv-export';
import ThinTimeSeries from './thin-time-series';
import { formatBytesPair, formatUnit, ROW_ACCENTS } from './readings';
import styles from './layered.module.scss';

export const DISK_HOT_PERCENT = 80;

export const countHotMounts = (rows: EntityTableRow[]) => (
  rows.filter((row) => (row.values.disk_used_percent ?? -1) >= DISK_HOT_PERCENT).length
);

type DiskSub = 'mount' | 'device';
type RateUnit = 'byteps' | 'cps' | 'ms' | 'percent';

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

const DiskSubButton = ({
  active,
  label,
  count,
  onClick
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) => (
  <button
    type="button"
    className={active ? `${styles.diskSubBtn} ${styles.diskSubBtnOn}` : styles.diskSubBtn}
    aria-pressed={active}
    onClick={onClick}
  >
    <span>{label}</span>
    <span className={styles.diskSubCount}>{count}</span>
  </button>
);

const legendReading = (value: number | null | undefined, unit: RateUnit) => {
  if (value == null || !Number.isFinite(value)) return undefined;
  return formatUnit(value, unit);
};

const DEVICE_CHARTS: Array<{
  key: string;
  titleKey: HostCategoryCopyKey;
  unit: RateUnit;
  series: Array<{ key: string; labelKey: HostCategoryCopyKey; color: string }>;
}> = [
  {
    key: 'throughput',
    titleKey: 'readWriteThroughput',
    unit: 'byteps',
    series: [
      { key: 'diskio_read_bytes_rate', labelKey: 'read', color: HOST_SERIES_COLOR.diskRead },
      { key: 'diskio_write_bytes_rate', labelKey: 'write', color: HOST_SERIES_COLOR.diskWrite }
    ]
  },
  {
    key: 'iops',
    titleKey: 'readWriteIops',
    unit: 'cps',
    series: [
      { key: 'diskio_reads_rate', labelKey: 'read', color: HOST_SERIES_COLOR.diskRead },
      { key: 'diskio_writes_rate', labelKey: 'write', color: HOST_SERIES_COLOR.diskWrite }
    ]
  },
  {
    key: 'latency',
    titleKey: 'rwLatency',
    unit: 'ms',
    series: [
      { key: 'disk_read_latency', labelKey: 'read', color: HOST_SERIES_COLOR.diskRead },
      { key: 'disk_write_latency', labelKey: 'write', color: HOST_SERIES_COLOR.diskWrite }
    ]
  },
  {
    key: 'util',
    titleKey: 'ioUtilization',
    unit: 'percent',
    series: [
      { key: 'diskio_io_util', labelKey: 'ioUtilization', color: HOST_SERIES_COLOR.diskUsed }
    ]
  }
];

export default function DiskPane({
  mountRows,
  deviceRows,
  loading,
  errorText,
  selectedMountKey,
  selectedDeviceKey,
  onSelectMount,
  onSelectDevice,
  hostLabel,
  windowsHost
}: {
  mountRows: EntityTableRow[];
  deviceRows: EntityTableRow[];
  loading: boolean;
  errorText?: string;
  selectedMountKey: string;
  selectedDeviceKey: string;
  onSelectMount: (key: string) => void;
  onSelectDevice: (key: string) => void;
  hostLabel: string;
  windowsHost?: boolean;
}) {
  const { t } = useDashboardText();
  const [sub, setSub] = useState<DiskSub>('mount');
  const selectedMount = mountRows.find((row) => row.key === selectedMountKey) || mountRows[0] || null;
  const selectedDevice = deviceRows.find((row) => row.key === selectedDeviceKey) || deviceRows[0] || null;
  const showFsType = showDiskFsTypeColumn(mountRows);
  const showInode = showDiskInodeColumn(mountRows, Boolean(windowsHost));
  const showMountBody = loading || mountRows.length > 0;
  const showDeviceBody = loading || deviceRows.length > 0;
  const emptyText = hostCategoryText(t, 'noData');
  const mountPath = selectedMount?.labels.path || selectedMount?.labels.mount || '';
  const mountTitle = mountPath
    ? hostCategoryText(t, 'mountUsedNamed', { name: mountPath })
    : hostCategoryText(t, 'mountUsed');
  const mountSeries = selectedMount?.series.disk_used_percent;
  const mountPoints = mountSeries || [];
  const mountChartData = useMemo(
    () => pointsToChartData(mountSeries?.length ? [{ points: mountSeries }] : []),
    [mountSeries]
  );
  const deviceChartModels = useMemo(() => DEVICE_CHARTS.map((chart) => {
    const present = chart.series.filter((item) => (selectedDevice?.series[item.key] || []).length > 0);
    return {
      chart,
      present,
      data: pointsToChartData(present.map((item) => ({
        points: selectedDevice?.series[item.key] || []
      })))
    };
  }), [selectedDevice]);

  const openDevice = (key: string) => {
    onSelectDevice(key);
    setSub('device');
  };
  const mountColumns: LayeredColumn[] = [
    {
      key: 'path',
      title: '挂载点',
      labelKey: 'path',
      width: 200,
      csvValue: (row) => row.labels.path || '—',
      render: (row, index) => {
        const path = row.labels.path || '';
        return (
          <span className={`${styles.nameCell} ${styles.nameCellTruncate}`}>
            <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
            <Tooltip title={path || undefined}>
              <span className={styles.pathEllipsis}>{path || '—'}</span>
            </Tooltip>
          </span>
        );
      }
    },
    { key: 'disk_used_percent', title: '使用率', unit: 'percent', bar: true, emptyDash: true },
    {
      key: 'disk_used',
      title: '已用/总量',
      csvValue: (row) => formatBytesPair(row.values.disk_used, row.values.disk_total),
      render: (row) => formatBytesPair(row.values.disk_used, row.values.disk_total)
    },
    {
      key: 'io_device',
      title: hostCategoryText(t, 'relatedDevice'),
      labelKey: 'io_device',
      csvValue: (row) => row.labels.io_device || '—',
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
              openDevice(device.key);
            }}
          >
            {name}
          </button>
        );
      }
    },
    ...(showInode ? [{
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
  ];
  const deviceColumns: LayeredColumn[] = [
    {
      key: 'name',
      title: '设备',
      labelKey: 'name',
      csvValue: (row) => row.labels.name || '—',
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
      csvValue: (row) => formatLatencyPair(row),
      render: (row) => formatLatencyPair(row)
    },
    {
      key: 'mounts',
      title: '挂载点',
      ellipsis: false,
      csvValue: (row) => {
        const paths = relatedMounts(mountRows, row.labels.name || '');
        return paths.length ? paths.join('; ') : '—';
      },
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
  ];

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {errorText ? <div className={styles.note}>{errorText}</div> : null}

      <div className={styles.diskSubBar}>
        <div className={styles.diskSubSwitch}>
          <DiskSubButton
            active={sub === 'mount'}
            label={hostCategoryText(t, 'mounts')}
            count={mountRows.length}
            onClick={() => setSub('mount')}
          />
          <DiskSubButton
            active={sub === 'device'}
            label={hostCategoryText(t, 'blockDevices')}
            count={deviceRows.length}
            onClick={() => setSub('device')}
          />
        </div>
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>
          {hostCategoryText(t, 'viewTrend')}
        </div>
      </div>

      {sub === 'mount' ? (
        <>
          <div className={styles.diskMountChart}>
            <ThinTimeSeries
              title={mountTitle}
              loading={loading && mountPoints.length === 0}
              unit="percent"
              emptyText={emptyText}
              data={mountChartData}
              legends={[{
                label: hostCategoryText(t, 'utilization'),
                color: HOST_SERIES_COLOR.diskUsed
              }]}
            />
          </div>
          <div className={styles.sectionHead}>
            <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>
              {hostCategoryText(t, 'mountList')}
            </div>
          </div>
          {showMountBody ? (
            <LayeredEntityTable
              rows={mountRows}
              loading={loading}
              selectedKey={selectedMount?.key || ''}
              onSelect={onSelectMount}
              emptyText={hostCategoryText(t, 'noMountPoints')}
              columns={mountColumns}
              toolbar={<TableCsvExportButton host={hostLabel} slug="mounts" columns={mountColumns} rows={mountRows} />}
            />
          ) : (
            <div className={`${classic.panel} ${styles.tableWrap}`}>
              <div className="flex justify-end">
                <TableCsvExportButton host={hostLabel} slug="mounts" columns={mountColumns} rows={mountRows} />
              </div>
              <div className={styles.note}>{hostCategoryText(t, 'noMountPoints')}</div>
            </div>
          )}
        </>
      ) : (
        <>
          <div className={`${styles.chartGrid2} ${styles.diskDeviceCharts}`}>
            {deviceChartModels.map(({ chart, present, data }) => {
              const legendSource = present.length ? present : chart.series;
              return (
                <ThinTimeSeries
                  key={chart.key}
                  title={hostCategoryText(t, chart.titleKey)}
                  loading={loading && present.length === 0}
                  unit={chart.unit}
                  emptyText={emptyText}
                  data={data}
                  legends={legendSource.map((item) => {
                    const reading = present.length
                      ? legendReading(latestPreferSignal(selectedDevice?.series[item.key]), chart.unit)
                      : undefined;
                    return {
                      label: hostCategoryText(t, item.labelKey),
                      color: item.color,
                      ...(reading ? { reading } : {})
                    };
                  })}
                />
              );
            })}
          </div>
          <div className={styles.sectionHead}>
            <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>
              {hostCategoryText(t, 'blockDeviceList')}
            </div>
          </div>
          {showDeviceBody ? (
            <LayeredEntityTable
              rows={deviceRows}
              loading={loading}
              selectedKey={selectedDevice?.key || ''}
              onSelect={onSelectDevice}
              emptyText={hostCategoryText(t, 'noBlockDevices')}
              columns={deviceColumns}
              toolbar={<TableCsvExportButton host={hostLabel} slug="devices" columns={deviceColumns} rows={deviceRows} />}
            />
          ) : (
            <div className={`${classic.panel} ${styles.tableWrap}`}>
              <div className="flex justify-end">
                <TableCsvExportButton host={hostLabel} slug="devices" columns={deviceColumns} rows={deviceRows} />
              </div>
              <div className={styles.note}>{hostCategoryText(t, 'noBlockDevices')}</div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
