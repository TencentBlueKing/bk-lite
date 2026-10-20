'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { GrayTabEmptyState, ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { KpiStrip, type KpiCardModel } from '../../host/layered/signal-bar';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import {
  formatMysqlReplicationLag,
  MYSQL_REPLICATION_EXTRA_METRICS,
  readMysqlReplicationExtras,
  readMysqlRoleBlock,
  type MysqlReplicationCard,
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
  return (
    <div
      className="[&>section>div]:flex [&>section>div]:min-h-[280px] [&>section>div]:items-center [&>section>div]:justify-center"
      data-replication-state={title === '加载中' ? 'loading' : 'empty'}
    >
      <GrayTabEmptyState title={title} />
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

  const statusBlock = block && block.kind !== 'primary' && block.fields.length > 0 ? block : null;
  const fields = statusBlock
    ? (statusBlock.kind === 'replica' ? replicaFields(statusBlock.fields) : statusBlock.fields)
    : [];
  const change = lagChange(statusBlock?.delay);
  const items: KpiCardModel[] = fields.map((field) => ({
    key: field.label,
    label: field.label,
    value: displayValue(field),
    tone: toneColor(field),
    subtitle: field.label === '复制延迟' ? change : undefined
  }));
  const showTrend = Boolean(statusBlock && (statusBlock.kind === 'replica' || statusBlock.delay?.length));
  const hasContent = items.length > 0
    || Boolean(extras?.error)
    || Boolean(extras?.logs.length)
    || Boolean(extras?.downstream.length)
    || showTrend;

  const replicationLoading = blocksUntilReady(MYSQL_ROLE_METRICS, pendingMetricNames)
    || blocksUntilReady(MYSQL_REPLICATION_EXTRA_METRICS, pendingMetricNames);
  if (!hasContent && replicationLoading) return <FillState title="加载中" />;
  if (!hasContent) return <FillState title="暂无复制数据" />;

  return (
    <div data-replication-state="ready">
      {items.length > 0 || extras?.error ? (
        <>
          <ProSectionTitle>状态</ProSectionTitle>
          {items.length > 0 ? (
            <div className="mt-3 [&>div]:!grid-cols-3">
              <KpiStrip items={items} />
            </div>
          ) : null}
          {extras?.error ? <CardRow cards={[extras.error]} /> : null}
        </>
      ) : null}
      {extras && extras.logs.length > 0 ? (
        <>
          <div className="mt-3">
            <ProSectionTitle>位点与日志</ProSectionTitle>
          </div>
          <CardRow cards={extras.logs} />
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
      {showTrend ? (
        <>
          <div className="mt-3">
            <ProSectionTitle>趋势</ProSectionTitle>
          </div>
          <div className={`mt-3 ${pro.perfGrid}`}>
            <div className={pro.perfWide}>
              <ThinTimeSeries
                title="复制延迟"
                unit="s"
                data={statusBlock?.delay || []}
                emptyText="暂无数据"
                legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
