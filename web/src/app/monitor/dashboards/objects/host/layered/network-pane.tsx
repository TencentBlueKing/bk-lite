'use client';

import React, { useMemo } from 'react';
import { HOST_PALETTE } from '../config';
import { latestFinite, pointsToChartData, sumPoints, type EntityTableRow } from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatUnit, ROW_ACCENTS } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const withRates = (rows: EntityTableRow[]): EntityTableRow[] => rows.map((row) => {
  const err = sumPoints(row.series.net_err_in_rate, row.series.net_err_out_rate);
  const drop = sumPoints(row.series.net_drop_in_rate, row.series.net_drop_out_rate);
  return {
    ...row,
    values: {
      ...row.values,
      err: err.length ? latestFinite(err) : null,
      drop: drop.length ? latestFinite(drop) : null
    },
    series: {
      ...row.series,
      err,
      drop
    }
  };
});

export default function NetworkPane({
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
  const viewRows = useMemo(() => withRates(rows), [rows]);
  const selected = viewRows.find((row) => row.key === selectedKey) || viewRows[0];
  const name = selected?.labels.interface || '';
  const hasErr = viewRows.some((row) => (row.series.err || []).length > 0);
  const hasDrop = viewRows.some((row) => (row.series.drop || []).length > 0);
  const showErrors = hasErr || hasDrop;
  const errLatest = selected?.values.err ?? null;
  const dropLatest = selected?.values.drop ?? null;
  const errorSeries = [
    ...(hasErr ? [{ points: selected?.series.err || [], label: 'err', color: HOST_PALETTE.rose }] : []),
    ...(hasDrop ? [{ points: selected?.series.drop || [], label: 'drop', color: HOST_PALETTE.orange }] : [])
  ];

  return (
    <>
      {errorText ? <div className={styles.note}>{errorText}</div> : null}
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>Metrics · 选中网卡</div>
        <div className={styles.hint}>{`选中行驱动上图 · 默认最忙${name ? ` ${name}` : ''} · 非整机合计`}</div>
      </div>
      <div className={showErrors ? styles.chartGrid3 : styles.chartGrid2}>
        <ThinTimeSeries
          key={`in-${selected?.key || 'none'}`}
          title={name ? `入流量 · ${name}` : '入流量'}
          reading={formatUnit(selected?.values.net_bytes_recv_rate ?? null, 'byteps')}
          loading={loading}
          unit="byteps"
          data={pointsToChartData([{ points: selected?.series.net_bytes_recv_rate || [] }])}
          legends={[{ label: '入', color: HOST_PALETTE.blue }]}
        />
        <ThinTimeSeries
          key={`out-${selected?.key || 'none'}`}
          title={name ? `出流量 · ${name}` : '出流量'}
          reading={formatUnit(selected?.values.net_bytes_sent_rate ?? null, 'byteps')}
          loading={loading}
          unit="byteps"
          data={pointsToChartData([{ points: selected?.series.net_bytes_sent_rate || [] }])}
          legends={[{ label: '出', color: HOST_PALETTE.cyan }]}
        />
        {showErrors ? (
          <ThinTimeSeries
            key={`err-${selected?.key || 'none'}`}
            title={name ? `错误 / 丢包 · ${name}` : '错误 / 丢包'}
            reading={`${formatUnit(errLatest, 'cps')} / ${formatUnit(dropLatest, 'cps')}`}
            loading={loading}
            unit="cps"
            data={pointsToChartData(errorSeries)}
            legends={errorSeries.map((item) => ({ label: item.label, color: item.color }))}
          />
        ) : null}
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>网络</div>
        <div className={styles.hint}>选中行驱动上图 · 可采列</div>
      </div>
      <LayeredEntityTable
        rows={viewRows}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        columns={[
          {
            key: 'interface',
            title: '网卡名',
            labelKey: 'interface',
            render: (row, index) => (
              <span className={styles.nameCell}>
                <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
                {row.labels.interface || '—'}
              </span>
            )
          },
          { key: 'net_bytes_recv_rate', title: '入', unit: 'byteps', emptyDash: true },
          { key: 'net_bytes_sent_rate', title: '出', unit: 'byteps', emptyDash: true },
          ...(hasErr ? [{ key: 'err', title: 'err', unit: 'cps' as const, emptyDash: true }] : []),
          ...(hasDrop ? [{ key: 'drop', title: 'drop', unit: 'cps' as const, emptyDash: true }] : [])
        ]}
      />
      <div className={styles.footnote}>可采：网卡名 / 入 / 出 / err / drop。本页是选中网卡，与概览「整机合计」不是同一条序列。</div>
    </>
  );
}
