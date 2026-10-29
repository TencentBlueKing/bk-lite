'use client';

import React, { useMemo } from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../config';
import { hostCategoryText } from './category-copy';
import { latestFinite, pointsToChartData, sumPoints, type EntityTableRow } from '../entity-series';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import TableCsvExportButton from './table-csv-export';
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
  onSelect,
  hostLabel
}: {
  rows: EntityTableRow[];
  loading: boolean;
  errorText?: string;
  selectedKey: string;
  onSelect: (key: string) => void;
  hostLabel: string;
}) {
  const viewRows = useMemo(() => withRates(rows), [rows]);
  const selected = viewRows.find((row) => row.key === selectedKey) || viewRows[0];
  const name = selected?.labels.interface || '';
  const hasErr = viewRows.some((row) => (row.series.err || []).length > 0);
  const hasDrop = viewRows.some((row) => (row.series.drop || []).length > 0);
  const errLatest = selected?.values.err ?? null;
  const dropLatest = selected?.values.drop ?? null;
  const errorSeries = [
    ...(hasErr ? [{ points: selected?.series.err || [], label: '错误', color: HOST_PALETTE.rose, latest: errLatest }] : []),
    ...(hasDrop ? [{ points: selected?.series.drop || [], label: '丢包', color: HOST_PALETTE.orange, latest: dropLatest }] : [])
  ];
  const { t } = useDashboardText();
  const nicColumns: LayeredColumn[] = [
    {
      key: 'interface',
      title: '网卡',
      labelKey: 'interface',
      csvValue: (row) => row.labels.interface || '—',
      render: (row, index) => (
        <span className={styles.nameCell}>
          <span className={styles.rowDot} style={{ background: ROW_ACCENTS[index % ROW_ACCENTS.length] }} />
          {row.labels.interface || '—'}
        </span>
      )
    },
    { key: 'net_bytes_recv_rate', title: '入', unit: 'byteps', emptyDash: true },
    { key: 'net_bytes_sent_rate', title: '出', unit: 'byteps', emptyDash: true },
    ...(hasErr ? [{ key: 'err', title: '错误', unit: 'cps' as const, emptyDash: true }] : []),
    ...(hasDrop ? [{ key: 'drop', title: '丢包', unit: 'cps' as const, emptyDash: true }] : [])
  ];
  const throughputTitle = name
    ? hostCategoryText(t, 'inboundOutboundThroughputNamed', { name })
    : hostCategoryText(t, 'inboundOutboundThroughput');
  const throughputItems = [
    { key: 'net_bytes_recv_rate' as const, label: hostCategoryText(t, 'inboundPacketRate'), color: HOST_SERIES_COLOR.netIn },
    { key: 'net_bytes_sent_rate' as const, label: hostCategoryText(t, 'outboundPacketRate'), color: HOST_SERIES_COLOR.netOut }
  ].filter((item) => (selected?.series[item.key] || []).length > 0);
  const packetItems = [
    { key: 'net_packets_recv_rate' as const, label: hostCategoryText(t, 'inboundPacketRate'), color: HOST_SERIES_COLOR.netIn },
    { key: 'net_packets_sent_rate' as const, label: hostCategoryText(t, 'outboundPacketRate'), color: HOST_SERIES_COLOR.netOut }
  ].filter((item) => (selected?.series[item.key] || []).length > 0);
  const chartData = useMemo(() => {
    const fromKeys = (keys: readonly string[]) => pointsToChartData(
      keys
        .filter((key) => (selected?.series[key] || []).length > 0)
        .map((key) => ({ points: selected?.series[key] || [] }))
    );
    return {
      throughput: fromKeys(['net_bytes_recv_rate', 'net_bytes_sent_rate']),
      error: pointsToChartData([
        ...(hasErr ? [{ points: selected?.series.err || [] }] : []),
        ...(hasDrop ? [{ points: selected?.series.drop || [] }] : [])
      ]),
      packet: fromKeys(['net_packets_recv_rate', 'net_packets_sent_rate'])
    };
  }, [hasDrop, hasErr, selected]);

  return (
    <>
      {errorText ? <div className={styles.note}>{errorText}</div> : null}
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>趋势</div>
      </div>
      <div className={styles.netTrendGrid}>
        <ThinTimeSeries
          title={throughputTitle}
          loading={loading}
          unit="byteps"
          data={chartData.throughput}
          legends={(throughputItems.length ? throughputItems : [
            { key: 'net_bytes_recv_rate' as const, label: hostCategoryText(t, 'inboundPacketRate'), color: HOST_SERIES_COLOR.netIn },
            { key: 'net_bytes_sent_rate' as const, label: hostCategoryText(t, 'outboundPacketRate'), color: HOST_SERIES_COLOR.netOut }
          ]).map((item) => ({
            label: item.label,
            color: item.color,
            reading: formatUnit(selected?.values[item.key] ?? null, 'byteps')
          }))}
        />
        <ThinTimeSeries
          title={name ? `错误 / 丢包 · ${name}` : '错误 / 丢包'}
          loading={loading}
          unit="cps"
          data={chartData.error}
          legends={errorSeries.map((item) => ({
            label: item.label,
            color: item.color,
            reading: formatUnit(item.latest, 'cps')
          }))}
        />
        <ThinTimeSeries
          title={name
            ? hostCategoryText(t, 'packetRateInOutNamed', { name })
            : hostCategoryText(t, 'packetRateInOut')}
          loading={loading}
          unit="cps"
          data={chartData.packet}
          legends={packetItems.map((item) => ({
            label: item.label,
            color: item.color,
            reading: formatUnit(selected?.values[item.key] ?? null, 'cps')
          }))}
        />
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>网卡列表</div>
      </div>
      <LayeredEntityTable
        rows={viewRows}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        emptyText="暂无网卡数据"
        columns={nicColumns}
        toolbar={<TableCsvExportButton host={hostLabel} slug="nics" columns={nicColumns} rows={viewRows} />}
      />
    </>
  );
}
