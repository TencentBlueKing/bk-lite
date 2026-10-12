'use client';

import React from 'react';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatBytesPair, formatPercent, formatUnit, percentTone, ROW_ACCENTS } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export const DISK_HOT_PERCENT = 80;

export const countHotMounts = (rows: EntityTableRow[]) => (
  rows.filter((row) => (row.values.disk_used_percent ?? -1) >= DISK_HOT_PERCENT).length
);

export default function DiskPane({
  rows,
  loading,
  errorText,
  selectedKey,
  onSelect
}: {
  rows: EntityTableRow[];
  loading: boolean;
  errorText?: string;
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  const selected = rows.find((row) => row.key === selectedKey) || rows[0];
  const path = selected?.labels.path || selected?.labels.mount || '';
  const ioDevice = selected?.labels.io_device || '';
  const used = selected?.values.disk_used_percent;
  const usedValue = used == null || !Number.isFinite(used) ? null : used;
  const readPoints = ioDevice ? (selected?.series.diskio_read_bytes_rate || []) : [];
  const writePoints = ioDevice ? (selected?.series.diskio_write_bytes_rate || []) : [];
  const readLatest = selected && ioDevice ? selected.values.diskio_read_bytes_rate : null;
  const writeLatest = selected && ioDevice ? selected.values.diskio_write_bytes_rate : null;

  return (
    <>
      {errorText ? <div className={styles.note}>{errorText}</div> : null}
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>Metrics</div>
        <div className={styles.hint}>
          {ioDevice || !selected
            ? '选中行驱动 · 默认最差挂载'
            : `选中 ${path || '挂载'} · 无 IO 设备`}
        </div>
      </div>
      <div className={styles.chartGrid3}>
        <ThinTimeSeries
          key={`used-${selected?.key || 'none'}`}
          title={path ? `挂载用量% · ${path}` : '挂载用量%'}
          reading={formatPercent(usedValue)}
          readingTone={percentTone(usedValue)}
          loading={loading}
          unit="percent"
          data={pointsToChartData([{ points: selected?.series.disk_used_percent || [] }])}
          legends={[{ label: path || 'used%', color: HOST_PALETTE.orange }]}
        />
        <ThinTimeSeries
          key={`read-${selected?.key || 'none'}-${ioDevice || 'empty'}`}
          title={ioDevice ? `设备读 · ${ioDevice}` : '设备读'}
          reading={ioDevice ? formatUnit(readLatest ?? null, 'byteps') : undefined}
          loading={loading && !selected}
          unit="byteps"
          emptyText={ioDevice ? '当前时间窗没有序列' : '无 IO 设备'}
          data={pointsToChartData([{ points: readPoints }])}
          legends={[{ label: '读', color: HOST_PALETTE.blue }]}
        />
        <ThinTimeSeries
          key={`write-${selected?.key || 'none'}-${ioDevice || 'empty'}`}
          title={ioDevice ? `设备写 · ${ioDevice}` : '设备写'}
          reading={ioDevice ? formatUnit(writeLatest ?? null, 'byteps') : undefined}
          loading={loading && !selected}
          unit="byteps"
          emptyText={ioDevice ? '当前时间窗没有序列' : '无 IO 设备'}
          data={pointsToChartData([{ points: writePoints }])}
          legends={[{ label: '写', color: HOST_PALETTE.cyan }]}
        />
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>磁盘</div>
        <div className={styles.hint}>选中行驱动上图 · 用量跟挂载 · IO 跟该行设备 · 无设备则 IO 空态</div>
      </div>
      <LayeredEntityTable
        rows={rows}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        columns={[
          {
            key: 'path',
            title: '挂载',
            labelKey: 'path',
            render: (row, index) => (
              <span className={styles.nameCell}>
                <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
                {row.labels.path || '—'}
              </span>
            )
          },
          { key: 'disk_used_percent', title: '用量', unit: 'percent', bar: true, emptyDash: true },
          {
            key: 'disk_used',
            title: '已用/总量',
            render: (row) => formatBytesPair(row.values.disk_used, row.values.disk_total)
          },
          {
            key: 'io_device',
            title: 'IO 设备',
            render: (row) => row.labels.io_device || '—'
          },
          { key: 'diskio_read_bytes_rate', title: '读', unit: 'byteps', emptyDash: true },
          { key: 'diskio_write_bytes_rate', title: '写', unit: 'byteps', emptyDash: true }
        ]}
      />
      <div className={styles.footnote}>用量跟挂载，IO 跟设备；对不上时 IO 为 —，读/写图留空。角标只统计 used%≥80 的挂载，为 0 不显示。</div>
    </>
  );
}
