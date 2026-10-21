'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { GrayTabEmptyState, KpiTileRow, ProSectionTitle, ThinTimeSeries, type KpiTileModel } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import {
  formatMysqlReplicationLag,
  MYSQL_REPLICATION_EXTRA_METRICS,
  readMysqlReplicationExtras,
  readMysqlReplicationSeries,
  readMysqlRoleBlock,
  type MysqlReplicationCard,
  type MysqlReplicationSeries,
  type MysqlRoleField,
  type MysqlRoleTone
} from './ia';
import type { MetricSeries } from '../types';
import { MYSQL_ROLE_METRICS, blocksUntilReady } from './section-loading';
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import pro from './pro.module.scss';

const TONE_COLOR: Record<MysqlRoleTone, string | undefined> = {
  ok: HOST_THRESHOLD_COLOR.ok,
  warn: HOST_THRESHOLD_COLOR.warn,
  muted: undefined
};

const REPLICA_LABELS = ['复制延迟', 'IO 线程', 'SQL 线程'] as const;
const THREAD_LABELS = new Set<string>(['IO 线程', 'SQL 线程']);
const FIELD_COPY: Record<string, MysqlCategoryCopyKey> = {
  复制延迟: 'replicationLag',
  'IO 线程': 'ioThread',
  'SQL 线程': 'sqlThread',
  已连接从库: 'connectedReplicas',
  已连从库: 'connectedReplicas',
  半同步: 'semisync',
  'Binlog 位点': 'binlogPosition',
  成员角色: 'memberRole',
  成员: 'members',
  流控: 'flowControl',
  冲突: 'conflict',
  复制错误: 'replicationError'
};
const VALUE_COPY: Record<string, MysqlCategoryCopyKey> = {
  运行中: 'running',
  已停止: 'stopped',
  已开启: 'enabled',
  已关闭: 'disabled'
};

const toneColor = (field: MysqlRoleField) => {
  if (field.value === '--') return undefined;
  if (THREAD_LABELS.has(field.label) && field.tone === 'warn') return HOST_THRESHOLD_COLOR.crit;
  return TONE_COLOR[field.tone];
};

const displayValue = (field: MysqlRoleField) => {
  if (field.value === '--' || !THREAD_LABELS.has(field.label)) return field.value;
  return `● ${field.value}`;
};

const lagChange = (points: ChartData[] | undefined) => {
  if (!points || points.length < 2) return undefined;
  const previous = points[points.length - 2]?.value1;
  const latest = points[points.length - 1]?.value1;
  if (typeof previous !== 'number' || typeof latest !== 'number') return undefined;
  const delta = latest - previous;
  if (Math.abs(delta) < 0.05) return '较上一点持平';
  const formatted = formatMysqlReplicationLag(Math.abs(delta));
  return `较上一点 ${delta > 0 ? '+' : '−'}${formatted}`;
};

const replicaFields = (fields: MysqlRoleField[]) => REPLICA_LABELS.map((label) => (
  fields.find((field) => field.label === label) || { label, value: '--', tone: 'muted' as const }
));

/** 从库，或已经采到延迟/位点时，铺三张趋势卡。缺的那张留空，不补零线。 */
const hasReplicationTrends = (
  kind: 'primary' | 'replica' | 'group' | undefined,
  trends: MysqlReplicationSeries
) => Boolean(
  kind === 'replica'
  || trends.delay.length
  || trends.relay.length
  || trends.binlog.length
  || trends.delayNote
  || trends.relayNote
  || trends.binlogNote
);

const REPL_LOADING_ITEMS: KpiTileModel[] = ['lag', 'io', 'sql'].map((key) => ({
  key,
  label: key,
  value: ''
}));

function FittedKpiRow({
  items,
  loading = false
}: {
  items: KpiTileModel[];
  loading?: boolean;
}) {
  return (
    <div
      className={pro.kpiFit}
      style={{ ['--kpi-cols' as string]: String(Math.max(items.length, 1)) }}
    >
      <KpiTileRow loading={loading} items={items} />
    </div>
  );
}

const extraItems = (cards: MysqlReplicationCard[]): KpiTileModel[] => (
  cards.map((card) => ({
    key: card.key,
    label: card.label,
    value: card.value,
    detail: card.detail,
    tone: TONE_COLOR[card.tone || 'muted'],
    alertLevel: card.tone === 'warn' ? 'warn' as const : undefined
  }))
);

function TrendCard({
  trend,
  title,
  unit,
  color,
  data,
  note,
  loading,
  emptyText
}: {
  trend: 'delay' | 'relay' | 'binlog';
  title: string;
  unit: 's' | 'counts';
  color: string;
  data: ChartData[];
  note?: string;
  loading?: boolean;
  emptyText: string;
}) {
  return (
    <div className={trend === 'delay' ? `${pro.perfWide} min-w-0` : 'min-w-0'} data-replication-trend={trend}>
      <ThinTimeSeries
        title={title}
        unit={unit}
        numericAxis
        loading={loading}
        data={data}
        reading={note}
        emptyText={emptyText}
        legends={[{ label: title, color }]}
      />
    </div>
  );
}

export default function ReplicationPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: Record<string, MetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
}) {
  const { t } = useDashboardText();
  const text = (key: MysqlCategoryCopyKey, values?: Record<string, string | number>) => (
    mysqlCategoryText(t, key, values)
  );
  const localizeLabel = (label: string) => {
    const key = FIELD_COPY[label];
    return key ? text(key) : label;
  };
  const localizeValue = (value: string) => {
    if (value.startsWith('● ')) {
      const inner = value.slice(2);
      const key = VALUE_COPY[inner];
      return key ? `● ${text(key)}` : value;
    }
    const key = VALUE_COPY[value];
    return key ? text(key) : value;
  };
  const lagUnits = { millisecond: text('millisecond'), second: text('second') };
  const block = useMemo(() => readMysqlRoleBlock(metricMap), [metricMap]);
  const extras = useMemo(() => readMysqlReplicationExtras(metricMap), [metricMap]);
  const trends = useMemo(() => readMysqlReplicationSeries(metricMap), [metricMap]);

  const statusBlock = block && block.kind !== 'primary' && block.fields.length > 0 ? block : null;
  const fields = statusBlock
    ? (statusBlock.kind === 'replica' ? replicaFields(statusBlock.fields) : statusBlock.fields)
    : [];
  const change = (() => {
    const raw = lagChange(statusBlock?.delay);
    if (!raw) return undefined;
    if (raw === '较上一点持平') return text('lagUnchanged');
    const points = statusBlock?.delay;
    if (!points || points.length < 2) return raw;
    const previous = points[points.length - 2]?.value1;
    const latest = points[points.length - 1]?.value1;
    if (typeof previous !== 'number' || typeof latest !== 'number') return raw;
    const delta = latest - previous;
    return text('lagDelta', {
      sign: delta > 0 ? '+' : '−',
      value: formatMysqlReplicationLag(Math.abs(delta), lagUnits)
    });
  })();
  const items: KpiTileModel[] = fields.map((field) => ({
    key: field.label,
    label: localizeLabel(field.label),
    value: localizeValue(displayValue(field)),
    tone: toneColor(field),
    subtitle: field.label === '复制延迟' ? change : undefined,
    alertLevel: THREAD_LABELS.has(field.label) && field.tone === 'warn'
      ? 'critical' as const
      : (field.tone === 'warn' ? 'warn' as const : undefined)
  }));
  const errorItems = extras?.error
    ? extraItems([{ ...extras.error, label: localizeLabel(extras.error.label) }])
    : [];
  const downstreamItems = extras?.downstream.length
    ? extraItems(extras.downstream.map((card) => ({
      ...card,
      label: localizeLabel(card.label),
      value: localizeValue(card.value)
    })))
    : [];
  const showTrends = hasReplicationTrends(statusBlock?.kind, trends);
  const hasContent = items.length > 0
    || errorItems.length > 0
    || downstreamItems.length > 0
    || showTrends;

  const replicationLoading = blocksUntilReady(MYSQL_ROLE_METRICS, pendingMetricNames)
    || blocksUntilReady(MYSQL_REPLICATION_EXTRA_METRICS, pendingMetricNames);
  const empty = text('noTrend');
  if (!hasContent && replicationLoading) {
    return (
      <div data-replication-state="loading">
        <ProSectionTitle>{text('status')}</ProSectionTitle>
        <FittedKpiRow loading items={REPL_LOADING_ITEMS} />
        <ProSectionTitle>{text('trend')}</ProSectionTitle>
        <div className={pro.perfGrid}>
          <TrendCard
            trend="delay"
            title={text('replicationLag')}
            unit="s"
            color={HOST_SERIES_COLOR.memUsed}
            data={[]}
            emptyText={empty}
            loading
          />
          <TrendCard
            trend="relay"
            title={text('relayPosition')}
            unit="counts"
            color={HOST_SERIES_COLOR.memAvailable}
            data={[]}
            emptyText={empty}
            loading
          />
          <TrendCard
            trend="binlog"
            title={text('binlogPosition')}
            unit="counts"
            color={HOST_SERIES_COLOR.diskUsed}
            data={[]}
            emptyText={empty}
            loading
          />
        </div>
      </div>
    );
  }
  if (!hasContent) {
    return (
      <div data-replication-state="empty">
        <GrayTabEmptyState title={text('noReplicationData')} />
      </div>
    );
  }

  return (
    <div data-replication-state="ready">
      {items.length > 0 || errorItems.length > 0 ? (
        <>
          <ProSectionTitle>{text('status')}</ProSectionTitle>
          {items.length > 0 ? <FittedKpiRow items={items} /> : null}
          {errorItems.length > 0 ? <FittedKpiRow items={errorItems} /> : null}
        </>
      ) : null}
      {downstreamItems.length > 0 ? (
        <>
          <ProSectionTitle>{text('primaryDownstream')}</ProSectionTitle>
          <FittedKpiRow items={downstreamItems} />
        </>
      ) : null}
      {showTrends ? (
        <>
          <ProSectionTitle>{text('trend')}</ProSectionTitle>
          <div className={pro.perfGrid}>
            <TrendCard
              trend="delay"
              title={text('replicationLag')}
              unit="s"
              color={HOST_SERIES_COLOR.memUsed}
              data={trends.delay}
              note={trends.delayNote}
              emptyText={empty}
              loading={trends.delay.length === 0 && pendingMetricNames.has('mysql_slave_seconds_behind_master')}
            />
            <TrendCard
              trend="relay"
              title={text('relayPosition')}
              unit="counts"
              color={HOST_SERIES_COLOR.memAvailable}
              data={trends.relay}
              note={trends.relayNote}
              emptyText={empty}
              loading={trends.relay.length === 0 && pendingMetricNames.has('mysql_slave_relay_log_pos')}
            />
            <TrendCard
              trend="binlog"
              title={text('binlogPosition')}
              unit="counts"
              color={HOST_SERIES_COLOR.diskUsed}
              data={trends.binlog}
              note={trends.binlogNote}
              emptyText={empty}
              loading={trends.binlog.length === 0 && pendingMetricNames.has('mysql_replication_source_log_pos')}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
