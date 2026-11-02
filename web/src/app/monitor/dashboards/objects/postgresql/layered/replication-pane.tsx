'use client';

import React, { useMemo } from 'react';
import {
  GrayTabEmptyState,
  ProDashLoading,
  ProSection,
  proChromeClass
} from '../../host/layered/pro-chrome';
import { PG_PALETTE } from '../config';
import { PostgresHint } from './hint';
import {
  readPostgresReplication,
  type PostgresReplicationNote
} from './replication';
import type { PostgresMetricMap } from './series';

const EMPTY = {
  title: '复制状态未采集',
  hint: '本窗口未见复制/恢复相关采点；确认采集任务在跑且至少一个周期已上报。',
  action: '查看采集配置'
};

const LAG_ABSENT = '本环境未采复制延迟/积压，不展示趋势。';

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
    body: '主库正在接受写入，备库还在回放变更。看不出是哪一种时显示 —。'
  },
  {
    key: 'streaming',
    label: '流复制连接数',
    body: '当前连着本实例的副本个数。大于 0 表示有副本连着。显示 0 表示现在没有副本连接，不代表延迟。'
  },
  {
    key: 'slots',
    label: '复制槽个数',
    body: '这台库上的复制槽个数，包括暂时没连上的槽。显示 0 表示现在没有复制槽，不代表有积压。'
  }
] as const;

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

  return (
    <div
      className="w-full shrink-0"
      data-postgres-replication-state={model.load === 'loading' ? 'loading' : 'ready'}
      data-postgres-replication-trends="none"
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
        <p
          className="m-0 text-[12px] leading-5 text-[var(--color-text-3)]"
          data-postgres-replication-lag-note=""
        >
          {LAG_ABSENT}
        </p>
      </ProSection>
    </div>
  );
}
