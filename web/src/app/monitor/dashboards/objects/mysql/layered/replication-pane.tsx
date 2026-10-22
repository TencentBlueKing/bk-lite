'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import {
  CardAlertDot,
  GrayTabEmptyState,
  KpiTileRow,
  ProSection,
  ThinTimeSeries,
  cardAlertClass,
  proChromeClass,
  type KpiTileModel
} from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import {
  MYSQL_REPLICATION_EXTRA_METRICS,
  readMysqlBinlogTrendEmpty,
  readMysqlReplicationExtras,
  readMysqlReplicationGap,
  readMysqlReplicationSeries,
  readMysqlRoleBlock,
  visibleReplicationTrends,
  type MysqlReplicationCard,
  type MysqlReplicationGap,
  type MysqlReplicationTrendKey,
  type MysqlRoleField
} from './ia';
import type { MetricSeries } from '../types';
import { MYSQL_ROLE_METRICS, blocksUntilReady } from './section-loading';
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import pro from './pro.module.scss';

const TONE_COLOR = {
  warn: HOST_THRESHOLD_COLOR.warn
};

/** 延迟正常保持深色。WARN 用告警橙，实心折角；超过 300 秒用告警红。线程运行中用成功绿，停止用告警红。 */
const statusTone = (field: MysqlRoleField) => {
  if (field.value === '--') return undefined;
  if (THREAD_LABELS.has(field.label)) {
    if (field.tone === 'ok') return HOST_THRESHOLD_COLOR.ok;
    if (field.tone === 'warn') return HOST_THRESHOLD_COLOR.crit;
    return undefined;
  }
  if (field.alertLevel === 'critical') return HOST_THRESHOLD_COLOR.crit;
  if (field.alertLevel === 'warn') return HOST_THRESHOLD_COLOR.warn;
  return undefined;
};

const threadDot = (field: MysqlRoleField): 'running' | 'stopped' | undefined => {
  if (field.value === '--' || !THREAD_LABELS.has(field.label)) return undefined;
  if (field.tone === 'ok') return 'running';
  if (field.tone === 'warn') return 'stopped';
  return undefined;
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

const replicaFields = (fields: MysqlRoleField[]) => REPLICA_LABELS.map((label) => (
  fields.find((field) => field.label === label) || { label, value: '--', tone: 'muted' as const }
));

const TREND_SPEC: Record<MysqlReplicationTrendKey, {
  title: MysqlCategoryCopyKey;
  unit: 's' | 'bytes';
  color: string;
  metric: string;
}> = {
  delay: {
    title: 'replicationLag',
    unit: 's',
    color: HOST_SERIES_COLOR.memUsed,
    metric: 'mysql_slave_seconds_behind_master'
  },
  relay: {
    title: 'relaySpace',
    unit: 'bytes',
    color: HOST_SERIES_COLOR.memAvailable,
    metric: 'mysql_slave_relay_log_space'
  },
  binlog: {
    title: 'binlogSize',
    unit: 'bytes',
    color: HOST_SERIES_COLOR.diskUsed,
    metric: 'mysql_binary_size_bytes'
  }
};

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

type StatusTile = KpiTileModel & { dot?: 'running' | 'stopped' };

/** 与健康 KPI 同壳。圆点单独着色，避免正常态把整段数值染成成功绿。 */
function StatusKpiRow({ items }: { items: StatusTile[] }) {
  return (
    <div
      className={pro.kpiFit}
      style={{ ['--kpi-cols' as string]: String(Math.max(items.length, 1)) }}
    >
      <div className={proChromeClass.kpiGrid}>
        {items.map((item) => (
          <div
            key={item.key}
            className={`${proChromeClass.kpiCard} ${cardAlertClass(item.alertLevel)}`}
            data-kpi={item.key}
          >
            <CardAlertDot level={item.alertLevel} />
            <div className={proChromeClass.kpiLabel}>{item.label}</div>
            <div className={item.subtitle ? proChromeClass.kpiValueRow : undefined}>
              <div className={proChromeClass.kpiValue} style={item.tone ? { color: item.tone } : undefined}>
                {item.dot ? (
                  <span className={pro.threadDot} aria-hidden="true">●</span>
                ) : null}
                {item.value}
              </div>
              {item.subtitle ? <div className={proChromeClass.kpiAside}>{item.subtitle}</div> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const extraItems = (cards: MysqlReplicationCard[]): KpiTileModel[] => (
  cards.map((card) => ({
    key: card.key,
    label: card.label,
    value: card.value,
    detail: card.detail,
    tone: card.alertLevel === 'critical'
      ? HOST_THRESHOLD_COLOR.crit
      : card.tone === 'warn'
        ? TONE_COLOR.warn
        : undefined,
    alertLevel: card.alertLevel === 'critical' || card.alertLevel === 'warn'
      ? card.alertLevel
      : undefined
  }))
);

/** 标题后直接接内容。spaced 只拉开上一整块到本块标题，不进标题和卡之间。 */
function ReplicationBlock({
  title,
  spaced = false,
  id,
  children
}: {
  title: string;
  spaced?: boolean;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <ProSection
      id={id}
      title={title}
      className={spaced ? `${pro.replBlock} ${pro.replBreak}` : pro.replBlock}
    >
      {children}
    </ProSection>
  );
}

function TrendCard({
  trend,
  title,
  unit,
  color,
  data,
  loading,
  emptyText,
  wide
}: {
  trend: MysqlReplicationTrendKey;
  title: string;
  unit: 's' | 'counts' | 'bytes';
  color: string;
  data: ChartData[];
  loading?: boolean;
  emptyText: string;
  wide?: boolean;
}) {
  return (
    <div className={wide ? `${pro.perfWide} min-w-0` : 'min-w-0'} data-replication-trend={trend}>
      <ThinTimeSeries
        title={title}
        unit={unit}
        numericAxis
        loading={loading}
        data={data}
        emptyText={emptyText}
        legends={[{ label: title, color }]}
      />
    </div>
  );
}

const gapPresentation = (
  gap: MysqlReplicationGap,
  text: (key: MysqlCategoryCopyKey) => string
) => {
  if (gap === 'partial') {
    return {
      title: text('replicationPartial'),
      hint: text('replicationPartialHint'),
      actionLabel: text('viewCollectionConfig')
    };
  }
  if (gap === 'not_collected') {
    return {
      title: text('replicationNotCollectedTitle'),
      hint: text('replicationNotCollectedHint'),
      actionLabel: text('enableReplicationCollection')
    };
  }
  if (gap === 'primary_no_slaves') {
    return {
      title: text('replicationPrimaryNoSlavesTitle'),
      hint: text('replicationPrimaryNoSlavesHint'),
      actionLabel: text('viewCollectionConfig')
    };
  }
  return {
    title: text('replicationUnconfigured'),
    hint: text('replicationUnconfiguredHint'),
    actionLabel: undefined
  };
};

export default function ReplicationPane({
  metricMap,
  pendingMetricNames,
  instanceName,
  onOpenCollection
}: {
  metricMap: Record<string, MetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
  instanceName: string;
  onOpenCollection: () => void;
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
    const key = VALUE_COPY[value];
    return key ? text(key) : value;
  };
  const block = useMemo(() => readMysqlRoleBlock(metricMap), [metricMap]);
  const extras = useMemo(() => readMysqlReplicationExtras(metricMap, text), [metricMap, text]);
  const trends = useMemo(() => readMysqlReplicationSeries(metricMap), [metricMap]);

  const statusBlock = block && block.kind !== 'primary'
    ? block
    : null;
  const fields = statusBlock?.kind === 'replica'
    ? replicaFields(statusBlock.fields)
    : (statusBlock?.fields || []);
  const items: StatusTile[] = fields.map((field) => ({
    key: field.label,
    label: localizeLabel(field.label),
    value: localizeValue(field.value),
    tone: statusTone(field),
    dot: threadDot(field),
    alertLevel: THREAD_LABELS.has(field.label) && field.tone === 'warn'
      ? 'critical' as const
      : (field.alertLevel === 'critical' || field.alertLevel === 'warn' ? field.alertLevel : undefined)
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
  const showStatus = items.length > 0 || errorItems.length > 0;
  const showDownstream = downstreamItems.length > 0;
  const slots = visibleReplicationTrends(statusBlock?.kind, trends);
  const showTrends = slots.length > 0;
  const hasContent = items.length > 0
    || errorItems.length > 0
    || downstreamItems.length > 0
    || showTrends;

  const replicationLoading = blocksUntilReady(MYSQL_ROLE_METRICS, pendingMetricNames)
    || blocksUntilReady(MYSQL_REPLICATION_EXTRA_METRICS, pendingMetricNames);
  const trendEmpty = (slot: MysqlReplicationTrendKey, metricName: string) => {
    if (slot === 'delay') return text('lagUnknown');
    if (slot === 'binlog') {
      return text(readMysqlBinlogTrendEmpty(metricMap, metricMap[metricName]?.loadState));
    }
    const series = metricMap[metricName];
    if (series?.loadState === 'success') return text('recentWindowEmpty');
    return text('relayCollectionOff');
  };
  if (!hasContent && replicationLoading) {
    return (
      <div data-replication-state="loading">
        <ReplicationBlock title={text('status')}>
          <FittedKpiRow loading items={REPL_LOADING_ITEMS} />
        </ReplicationBlock>
      </div>
    );
  }
  if (!hasContent) {
    const gap = readMysqlReplicationGap(metricMap, instanceName);
    const gapCopy = gapPresentation(gap, text);
    return (
      <div data-replication-state="empty" data-replication-gap={gap}>
        <GrayTabEmptyState
          title={gapCopy.title}
          hint={gapCopy.hint}
          actionLabel={gapCopy.actionLabel}
          onAction={gapCopy.actionLabel ? onOpenCollection : undefined}
        />
      </div>
    );
  }

  return (
    <div data-replication-state="ready">
      {showStatus ? (
        <ReplicationBlock title={text('status')}>
          {items.length > 0 ? <StatusKpiRow items={items} /> : null}
          {errorItems.length > 0 ? <FittedKpiRow items={errorItems} /> : null}
        </ReplicationBlock>
      ) : null}
      {showDownstream ? (
        <ReplicationBlock title={text('primaryDownstream')} spaced={showStatus}>
          <FittedKpiRow items={downstreamItems} />
        </ReplicationBlock>
      ) : null}
      {showTrends ? (
        <ReplicationBlock id="mysql-repl-trend" title={text('trend')} spaced={showStatus || showDownstream}>
          <div className={pro.perfGrid} data-replication-trends={slots.join(',')}>
            {slots.map((slot) => {
              const spec = TREND_SPEC[slot];
              const data = trends[slot];
              return (
                <TrendCard
                  key={slot}
                  trend={slot}
                  title={text(spec.title)}
                  unit={spec.unit}
                  color={spec.color}
                  data={data}
                  emptyText={trendEmpty(slot, spec.metric)}
                  wide={slots.length === 1 || slot === 'delay'}
                  loading={data.length === 0 && pendingMetricNames.has(spec.metric)}
                />
              );
            })}
          </div>
        </ReplicationBlock>
      ) : null}
    </div>
  );
}
