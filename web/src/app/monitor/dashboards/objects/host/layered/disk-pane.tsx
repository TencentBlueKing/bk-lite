'use client';

import React from 'react';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatBytesPair, formatPercent, formatUnit, ROW_ACCENTS } from './readings';
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
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>趋势</div>
        <div className={styles.hint}>
          {ioDevice || !selected ? '点击下表行切换' : '该挂载无关联磁盘设备'}
        </div>
      </div>
      <div className={styles.chartGrid3}>
        <ThinTimeSeries
          key={`used-${selected?.key || 'none'}`}
          title={path ? `使用率 · ${path}` : '使用率'}
          reading={formatPercent(usedValue)}
          loading={loading}
          unit="percent"
          data={pointsToChartData([{ points: selected?.series.disk_used_percent || [] }])}
          legends={[{ label: path || '使用率', color: HOST_PALETTE.orange }]}
        />
        <ThinTimeSeries
          key={`read-${selected?.key || 'none'}-${ioDevice || 'empty'}`}
          title={ioDevice ? `读取 · ${ioDevice}` : '读取'}
          reading={ioDevice ? formatUnit(readLatest ?? null, 'byteps') : undefined}
          loading={loading && !selected}
          unit="byteps"
          emptyText={ioDevice ? '暂无数据' : '无关联磁盘设备'}
          data={pointsToChartData([{ points: readPoints }])}
          legends={[{ label: '读取', color: HOST_PALETTE.blue }]}
        />
        <ThinTimeSeries
          key={`write-${selected?.key || 'none'}-${ioDevice || 'empty'}`}
          title={ioDevice ? `写入 · ${ioDevice}` : '写入'}
          reading={ioDevice ? formatUnit(writeLatest ?? null, 'byteps') : undefined}
          loading={loading && !selected}
          unit="byteps"
          emptyText={ioDevice ? '暂无数据' : '无关联磁盘设备'}
          data={pointsToChartData([{ points: writePoints }])}
          legends={[{ label: '写入', color: HOST_PALETTE.cyan }]}
        />
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>挂载点</div>
        <div className={styles.hint}>按使用率排序；选中后上方显示对应趋势</div>
      </div>
      <LayeredEntityTable
        rows={rows}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        emptyText="暂无挂载数据"
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
            title: '磁盘设备',
            render: (row) => row.labels.io_device || '—'
          },
          { key: 'diskio_read_bytes_rate', title: '读取', unit: 'byteps', emptyDash: true },
          { key: 'diskio_write_bytes_rate', title: '写入', unit: 'byteps', emptyDash: true }
        ]}
      />
    </>
  );
}
