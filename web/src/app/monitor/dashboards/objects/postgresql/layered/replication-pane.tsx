'use client';

import React, { useMemo } from 'react';
import {
  GrayTabEmptyState,
  ProDashLoading,
  ProSection,
  ThinTimeSeries,
  proChromeClass
} from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { PG_PALETTE } from '../config';
import { PostgresHint } from './hint';
import {
  readPostgresReplication,
  type PostgresReplicationLagCard,
  type PostgresReplicationLagKey,
  type PostgresReplicationNote
} from './replication';
import type { PostgresMetricMap } from './series';

const EMPTY = {
  title: '复制状态未采集',
  hint: '本窗口暂无复制或恢复相关数据。请确认采集已开启并完成至少一个上报周期。',
  action: '查看采集配置'
};

const LAG_ABSENT = '本窗口暂无复制延迟或积压数据。';

const NOTE_COPY: Record<Exclude<PostgresReplicationNote, 'none'>, { title: string; hint: string }> = {
  unconfigured: {
    title: '当前未配置复制',
    hint: '当前没有流复制连接，也没有复制槽。若这台库不需要从库，可以忽略。'
  },
  primary_no_downstream: {
    title: '主库 · 暂无下游',
    hint: '流复制连接数和复制槽都是 0。若本来没有从库，可以忽略；有从库时请核对流复制是否已连上。'
  }
};

const CARDS = [
  {
    key: 'role',
    label: '角色',
    body: '本实例当前是主库还是备库。\n主库：对外提供写入。\n备库：持续回放主库变更。\n暂无法判断时显示 —。'
  },
  {
    key: 'streaming',
    label: '流复制连接数',
    body: '当前连着本实例的副本个数。为 0 表示当前没有连接的副本，与延迟无关。'
  },
  {
    key: 'slots',
    label: '复制槽个数',
    body: '本实例上的复制槽个数，包括暂时没有连上的槽。为 0 表示当前没有复制槽，与积压无关。'
  }
] as const;

const LAG_COPY: Record<PostgresReplicationLagKey, { label: string; body: string; color: string }> = {
  write: {
    label: '写入延迟',
    body: '副本收到变更后，写到本地所花的最长时间。没有副本连着时，读数通常是 0。',
    color: PG_PALETTE.blue
  },
  flush: {
    label: '刷盘延迟',
    body: '副本把收到的变更落到磁盘所花的最长时间。没有副本连着时，读数通常是 0。',
    color: PG_PALETTE.cyan
  },
  replay: {
    label: '回放延迟',
    body: '副本把收到的变更应用到数据上所花的最长时间。没有副本连着时，读数通常是 0。',
    color: PG_PALETTE.indigo
  },
  backlog: {
    label: '复制槽积压',
    body: '为了让暂时断开的副本还能接上，复制槽留着的数据量。没有槽在留数据时，读数通常是 0。',
    color: PG_PALETTE.amber
  }
};

function StatusCard({
  cardKey,
  label,
  body,
  text,
  tone,
  loading,
  sample
}: {
  cardKey: string;
  label: string;
  body: string;
  text: string;
  tone?: string;
  loading: boolean;
  sample: number | null;
}) {
  return (
    <div
      className={`${proChromeClass.kpiCard}${loading ? ` ${proChromeClass.kpiCardLoading}` : ''}`}
      data-postgres-replication-card={cardKey}
      data-postgres-replication-value={loading ? 'loading' : sample == null ? 'missing' : String(sample)}
    >
      {loading ? <ProDashLoading /> : (
        <>
          <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
            <span className="min-w-0 truncate">{label}</span>
            <PostgresHint kind={`pg-replication-${cardKey}`} title={label} body={body} />
          </div>
          <div className={proChromeClass.kpiValue} style={tone ? { color: tone } : undefined}>
            {text}
          </div>
        </>
      )}
    </div>
  );
}

function LagValueCard({ card }: { card: PostgresReplicationLagCard }) {
  const copy = LAG_COPY[card.key];
  return (
    <div
      className={proChromeClass.kpiCard}
      data-postgres-replication-lag-card={card.key}
      data-postgres-replication-lag-value={card.value == null ? 'missing' : String(card.value)}
    >
      <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
        <span className="min-w-0 truncate">{copy.label}</span>
        <PostgresHint kind={`pg-replication-lag-${card.key}`} title={copy.label} body={copy.body} />
      </div>
      <div
        className={proChromeClass.kpiValue}
        style={card.value == null ? undefined : { color: copy.color }}
      >
        {card.text}
      </div>
    </div>
  );
}

function LagChart({ card }: { card: PostgresReplicationLagCard }) {
  const copy = LAG_COPY[card.key];
  return (
    <div className="min-w-0" data-postgres-replication-lag-chart={card.key} data-postgres-replication-lag-points={String(card.points.length)}>
      <ThinTimeSeries
        title={copy.label}
        unit={card.unit}
        data={card.points}
        legends={[{ label: copy.label, color: copy.color }]}
        emptyText={LAG_ABSENT}
        hintNode={<PostgresHint kind={`pg-replication-lag-chart-${card.key}`} title={copy.label} body={copy.body} />}
      />
    </div>
  );
}

export default function ReplicationPane({
  metricMap,
  pendingMetricNames,
  booting = false,
  onOpenCollection
}: {
  metricMap: PostgresMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  booting?: boolean;
  onOpenCollection?: () => void;
}) {
  const model = useMemo(
    () => readPostgresReplication(metricMap, pendingMetricNames, booting),
    [booting, metricMap, pendingMetricNames]
  );
  if (model.load === 'not_collected') {
    return (
      <div data-postgres-replication-state="empty">
        <GrayTabEmptyState
          title={EMPTY.title}
          hint={EMPTY.hint}
          actionLabel={onOpenCollection ? EMPTY.action : undefined}
          onAction={onOpenCollection}
        />
      </div>
    );
  }

  const note = model.load === 'ready' && model.note !== 'none' ? NOTE_COPY[model.note] : undefined;
  const roleTone = model.role === '主库'
    ? PG_PALETTE.emerald
    : model.role === '备库'
      ? PG_PALETTE.indigo
      : undefined;
  const cards = [
    {
      ...CARDS[0],
      text: model.roleText,
      tone: roleTone,
      loading: model.load === 'loading' || model.rolePending,
      sample: model.recovery
    },
    {
      ...CARDS[1],
      text: model.streamingText,
      tone: model.streaming == null ? undefined : PG_PALETTE.blue,
      loading: model.load === 'loading' || model.streamingPending,
      sample: model.streaming
    },
    {
      ...CARDS[2],
      text: model.slotsText,
      tone: model.slots == null ? undefined : PG_PALETTE.cyan,
      loading: model.load === 'loading' || model.slotsPending,
      sample: model.slots
    }
  ];

  const lagCharts = model.lag.cards.filter((card) => card.points.length > 0);
  const showLag = model.load !== 'loading';

  return (
    <div
      className="flex w-full min-w-0 shrink-0 flex-col gap-4"
      data-postgres-replication-state={model.load === 'loading' ? 'loading' : 'ready'}
      data-postgres-replication-trends={model.lag.trends}
    >
      <ProSection title="状态" className="!gap-2">
        <div
          className={proChromeClass.kpiGrid}
          style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
          data-postgres-replication-status=""
        >
          {cards.map((card) => (
            <StatusCard
              key={card.key}
              cardKey={card.key}
              label={card.label}
              body={card.body}
              text={card.text}
              tone={card.tone}
              loading={card.loading}
              sample={card.sample}
            />
          ))}
        </div>
        {note ? (
          <div
            className="rounded-[12px] border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2"
            data-postgres-replication-note={model.note}
          >
            <div className="text-[13px] font-semibold text-[var(--color-text-2)]">{note.title}</div>
            <div className="mt-1 text-[12px] leading-[1.5] text-[var(--color-text-3)]">{note.hint}</div>
          </div>
        ) : null}
      </ProSection>
      {showLag ? (
        <ProSection title="延迟与积压" className="!gap-2">
          {model.lag.state === 'loading' ? (
            <div
              className={`${proChromeClass.kpiCard} ${proChromeClass.kpiCardLoading}`}
              data-postgres-replication-lag="loading"
            >
              <ProDashLoading />
            </div>
          ) : null}
          {model.lag.state === 'absent' ? (
            <p
              className="m-0 text-[12px] leading-5 text-[var(--color-text-3)]"
              data-postgres-replication-lag="absent"
              data-postgres-replication-lag-note=""
            >
              {LAG_ABSENT}
            </p>
          ) : null}
          {model.lag.state === 'ready' ? (
            <>
              <div
                className={proChromeClass.kpiGrid}
                style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}
                data-postgres-replication-lag="ready"
              >
                {model.lag.cards.map((card) => (
                  <LagValueCard key={card.key} card={card} />
                ))}
              </div>
              {lagCharts.length > 0 ? (
                <div className={host.chartGrid2} data-postgres-replication-lag-charts="">
                  {lagCharts.map((card) => (
                    <LagChart key={card.key} card={card} />
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </ProSection>
      ) : null}
    </div>
  );
}
