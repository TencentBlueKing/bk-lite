'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { GrayTabEmptyState, ProDashLoading, ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
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
import pro from './pro.module.scss';

const TONE_COLOR: Record<MysqlRoleTone, string | undefined> = {
  ok: HOST_THRESHOLD_COLOR.ok,
  warn: HOST_THRESHOLD_COLOR.warn,
  muted: undefined
};

const REPLICA_LABELS = ['复制延迟', 'IO 线程', 'SQL 线程'] as const;
const THREAD_LABELS = new Set<string>(['IO 线程', 'SQL 线程']);

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
  const text = formatMysqlReplicationLag(Math.abs(delta));
  return `较上一点 ${delta > 0 ? '+' : '−'}${text}`;
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

function NoteCard({ card }: { card: MysqlReplicationCard }) {
  return (
    <section
      className="flex min-w-0 flex-col items-start rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2"
      data-replication-card={card.key}
    >
      <div className="text-[12px] font-medium leading-[14px] text-[var(--color-text-2)]">{card.label}</div>
      <div
        className="mt-1 break-words text-[16px] font-semibold leading-6 text-[var(--color-text-1)]"
        style={card.tone && card.tone !== 'muted' ? { color: TONE_COLOR[card.tone] } : undefined}
      >
        {card.value}
      </div>
      {card.detail ? (
        <div className="mt-1 break-words text-[12px] leading-4 text-[var(--color-text-3)]">{card.detail}</div>
      ) : null}
    </section>
  );
}

function CardRow({ cards }: { cards: MysqlReplicationCard[] }) {
  return (
    <div className={`mt-3 ${pro.perfGrid}`}>
      {cards.map((card) => (
        <div key={card.key} className={cards.length === 1 ? pro.perfWide : 'min-w-0'}>
          <NoteCard card={card} />
        </div>
      ))}
    </div>
  );
}

function FillState({ title }: { title: string }) {
  const loading = title === '加载中';
  return (
    <div
      className="[&>section>div]:flex [&>section>div]:min-h-[280px] [&>section>div]:items-center [&>section>div]:justify-center"
      data-replication-state={loading ? 'loading' : 'empty'}
    >
      {loading ? (
        <section className={`${classic.panel} ${host.chartPanel}`}>
          <div className={host.chartEmpty}>
            <ProDashLoading />
          </div>
        </section>
      ) : (
        <GrayTabEmptyState title={title} />
      )}
    </div>
  );
}

function StatusCards({
  items
}: {
  items: Array<{ key: string; label: string; value: string; tone?: string; subtitle?: string }>;
}) {
  return (
    <div className="mt-3 grid grid-cols-3 gap-3">
      {items.map((item) => (
        <section key={item.key} className={host.kpiCard} data-kpi={item.key}>
          <div className={host.kpiLabel}>{item.label}</div>
          <div
            className="mt-1 max-w-full truncate text-[18px] font-semibold leading-6 tracking-[-0.02em] text-[var(--color-text-1)] [font-variant-numeric:tabular-nums]"
            style={item.tone ? { color: item.tone } : undefined}
          >
            {item.value}
          </div>
          {item.subtitle ? (
            <div className="mt-1 max-w-full truncate text-[12px] leading-4 text-[var(--color-text-3)]">{item.subtitle}</div>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function TrendCard({
  trend,
  title,
  unit,
  color,
  data,
  note,
  loading
}: {
  trend: 'delay' | 'relay' | 'binlog';
  title: string;
  unit: 's' | 'counts';
  color: string;
  data: ChartData[];
  note?: string;
  loading?: boolean;
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
        emptyText="暂无数据"
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
  const block = useMemo(() => readMysqlRoleBlock(metricMap), [metricMap]);
  const extras = useMemo(() => readMysqlReplicationExtras(metricMap), [metricMap]);
  const trends = useMemo(() => readMysqlReplicationSeries(metricMap), [metricMap]);

  const statusBlock = block && block.kind !== 'primary' && block.fields.length > 0 ? block : null;
  const fields = statusBlock
    ? (statusBlock.kind === 'replica' ? replicaFields(statusBlock.fields) : statusBlock.fields)
    : [];
  const change = lagChange(statusBlock?.delay);
  const items = fields.map((field) => ({
    key: field.label,
    label: field.label,
    value: displayValue(field),
    tone: toneColor(field),
    subtitle: field.label === '复制延迟' ? change : undefined
  }));
  const showTrends = hasReplicationTrends(statusBlock?.kind, trends);
  const hasContent = items.length > 0
    || Boolean(extras?.error)
    || Boolean(extras?.downstream.length)
    || showTrends;

  const replicationLoading = blocksUntilReady(MYSQL_ROLE_METRICS, pendingMetricNames)
    || blocksUntilReady(MYSQL_REPLICATION_EXTRA_METRICS, pendingMetricNames);
  if (!hasContent && replicationLoading) return <FillState title="加载中" />;
  if (!hasContent) return <FillState title="暂无复制数据" />;

  return (
    <div data-replication-state="ready">
      {items.length > 0 || extras?.error ? (
        <>
          <ProSectionTitle>状态</ProSectionTitle>
          {items.length > 0 ? <StatusCards items={items} /> : null}
          {extras?.error ? <CardRow cards={[extras.error]} /> : null}
        </>
      ) : null}
      {extras && extras.downstream.length > 0 ? (
        <>
          <div className="mt-3">
            <ProSectionTitle>主库下游</ProSectionTitle>
          </div>
          <CardRow cards={extras.downstream} />
        </>
      ) : null}
      {showTrends ? (
        <>
          <div className="mt-3">
            <ProSectionTitle>趋势</ProSectionTitle>
          </div>
          <div className={`mt-3 ${pro.perfGrid}`}>
            <TrendCard
              trend="delay"
              title="复制延迟"
              unit="s"
              color={HOST_SERIES_COLOR.memUsed}
              data={trends.delay}
              note={trends.delayNote}
              loading={trends.delay.length === 0 && pendingMetricNames.has('mysql_slave_seconds_behind_master')}
            />
            <TrendCard
              trend="relay"
              title="Relay 位点"
              unit="counts"
              color={HOST_SERIES_COLOR.memAvailable}
              data={trends.relay}
              note={trends.relayNote}
              loading={trends.relay.length === 0 && pendingMetricNames.has('mysql_slave_relay_log_pos')}
            />
            <TrendCard
              trend="binlog"
              title="Binlog 位点"
              unit="counts"
              color={HOST_SERIES_COLOR.diskUsed}
              data={trends.binlog}
              note={trends.binlogNote}
              loading={trends.binlog.length === 0 && pendingMetricNames.has('mysql_replication_source_log_pos')}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
