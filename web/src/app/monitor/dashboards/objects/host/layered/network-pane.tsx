'use client';

import React, { useMemo } from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_PALETTE } from '../config';
import { hostCategoryText } from './category-copy';
import { latestFinite, pointsToChartData, rowHasSeries, sumPoints, type EntityTableRow } from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatUnit, ROW_ACCENTS } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const PACKET_KEYS = ['net_packets_recv_rate', 'net_packets_sent_rate'] as const;

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
    ...(hasErr ? [{ points: selected?.series.err || [], label: '错误', color: HOST_PALETTE.rose, latest: errLatest }] : []),
    ...(hasDrop ? [{ points: selected?.series.drop || [], label: '丢包', color: HOST_PALETTE.orange, latest: dropLatest }] : [])
  ];
  const { t } = useDashboardText();
  const packetItems = [
    { key: 'net_packets_recv_rate' as const, label: hostCategoryText(t, 'inboundPacketRate'), color: HOST_PALETTE.blue },
    { key: 'net_packets_sent_rate' as const, label: hostCategoryText(t, 'outboundPacketRate'), color: HOST_PALETTE.cyan }
  ].filter((item) => (selected?.series[item.key] || []).length > 0);
  const showPackets = rowHasSeries(selected, PACKET_KEYS);

  return (
    <>
      {errorText ? <div className={styles.note}>{errorText}</div> : null}
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>趋势</div>
      </div>
      <div className={showErrors ? styles.chartGrid3 : styles.chartGrid2}>
        <ThinTimeSeries
          key={`in-${selected?.key || 'none'}`}
          title={name
            ? hostCategoryText(t, 'inboundThroughputNamed', { name })
            : hostCategoryText(t, 'inboundThroughput')}
          loading={loading}
          unit="byteps"
          data={pointsToChartData([{ points: selected?.series.net_bytes_recv_rate || [] }])}
          legends={[{
            label: '入',
            color: HOST_PALETTE.blue
          }]}
        />
        <ThinTimeSeries
          key={`out-${selected?.key || 'none'}`}
          title={name
            ? hostCategoryText(t, 'outboundThroughputNamed', { name })
            : hostCategoryText(t, 'outboundThroughput')}
          loading={loading}
          unit="byteps"
          data={pointsToChartData([{ points: selected?.series.net_bytes_sent_rate || [] }])}
          legends={[{
            label: '出',
            color: HOST_PALETTE.cyan
          }]}
        />
        {showErrors ? (
          <ThinTimeSeries
            key={`err-${selected?.key || 'none'}`}
            title={name ? `错误 / 丢包 · ${name}` : '错误 / 丢包'}
            loading={loading}
            unit="cps"
            data={pointsToChartData(errorSeries)}
            legends={errorSeries.map((item) => ({
              label: item.label,
              color: item.color,
              reading: formatUnit(item.latest, 'cps')
            }))}
          />
        ) : null}
      </div>

      {showPackets ? (
        <>
          <div className={styles.sectionHead}>
            <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'detailedMetrics')}</div>
          </div>
          <div className="grid grid-cols-1 gap-3">
            <ThinTimeSeries
              key={`pps-${selected?.key || 'none'}`}
              title={name
                ? hostCategoryText(t, 'packetRateInOutNamed', { name })
                : hostCategoryText(t, 'packetRateInOut')}
              loading={loading && !selected}
              unit="cps"
              data={pointsToChartData(packetItems.map((item) => ({
                points: selected?.series[item.key] || []
              })))}
              legends={packetItems.map((item) => ({
                label: item.label,
                color: item.color,
                reading: formatUnit(selected?.values[item.key] ?? null, 'cps')
              }))}
            />
          </div>
        </>
      ) : null}

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>网卡</div>
        <div className={styles.hint}>{hostCategoryText(t, 'chartFollowsSelection')}</div>
      </div>
      <LayeredEntityTable
        rows={viewRows}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        emptyText="暂无网卡数据"
        columns={[
          {
            key: 'interface',
            title: '网卡',
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
          ...(hasErr ? [{ key: 'err', title: '错误', unit: 'cps' as const, emptyDash: true }] : []),
          ...(hasDrop ? [{ key: 'drop', title: '丢包', unit: 'cps' as const, emptyDash: true }] : [])
        ]}
      />
    </>
  );
}
