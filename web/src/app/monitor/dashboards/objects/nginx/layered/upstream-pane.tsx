'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { Switch } from 'antd';
import { durationUnitLabel, formatBytes, formatCount, formatDuration, formatPerSecond, formatPlain } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxCompositionCard } from './nginx-composition';
import { NginxHint } from './nginx-hint';
import type { NginxDashboardModel, NginxSeriesItem, UpstreamGroupRow, UpstreamMemberRow } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';
import { ProMetricTable, type ProMetricColumn, type ProMetricRow } from '../../../shared/widgets/pro-metric-table';

const STATUS_COLORS: Record<string, string> = {
  '1xx': '#8c8c8c',
  '2xx': '#27c274',
  '3xx': '#2f6bff',
  '4xx': '#ff8a1f',
  '5xx': '#ff4d4f'
};
const STATUS_ORDER = ['1xx', '2xx', '3xx', '4xx', '5xx'] as const;
const CELL = 'flex min-w-0 min-[1100px]:col-span-3';
const THIRD = 'min-w-0 min-[1100px]:col-span-4';

const topSeries = (items: readonly NginxSeriesItem[]) => [...items]
  .sort((left, right) => (right.points[right.points.length - 1]?.value ?? 0) - (left.points[left.points.length - 1]?.value ?? 0))
  .slice(0, 5);

const textOf = (value: number | null | undefined, text: string) => (value == null ? '--' : text);

const memberState = (member: UpstreamMemberRow) => {
  if (member.down === 1) return { label: '已下线', className: 'bg-[color-mix(in_srgb,var(--color-fail)_14%,transparent)] text-[var(--color-fail)]' };
  if (member.backup === 1) return { label: '备份', className: 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]' };
  return { label: '在线', className: 'bg-[color-mix(in_srgb,var(--color-success)_14%,transparent)] text-[var(--color-success)]' };
};

const columns: ProMetricColumn[] = [
  { key: 'status', label: '状态', align: 'left' },
  { key: 'address', label: '地址', align: 'left', minWidth: 160 },
  { key: 'weight', label: '权重', align: 'right' },
  { key: 'rate', label: '请求速率', align: 'right' },
  { key: 'window', label: '窗口请求数', align: 'right' },
  { key: '4xx', label: '4xx', align: 'right' },
  { key: '5xx', label: '5xx', align: 'right' },
  { key: 'in', label: '入站', align: 'right' },
  { key: 'out', label: '出站', align: 'right' },
  { key: 'request', label: '请求处理时间', align: 'right' },
  { key: 'response', label: '响应时间', align: 'right' },
  { key: 'maxFails', label: '最大失败次数', align: 'right' },
  { key: 'failTimeout', label: '失败暂停时长', align: 'right' }
];

export default function UpstreamPane({
  model,
  phases,
  emptyText,
  onRetry,
  onRetryFailed
}: {
  model: NginxDashboardModel;
  phases: Readonly<Record<string, NginxQueryPhase>>;
  emptyText: string;
  onRetry: (keys: readonly string[]) => void;
  onRetryFailed: () => void;
}) {
  const [downOnly, setDownOnly] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDesc, setSortDesc] = useState(true);
  const board = model.board;
  const kpiPhase = phaseOf(NGINX_CARD_QUERIES.upstreamKpi, phases);
  const trendPhase = phaseOf(NGINX_CARD_QUERIES.upstreamTrend, phases);
  const statusPhase = phaseOf(NGINX_CARD_QUERIES.upstreamStatus, phases);
  const timePhase = phaseOf(NGINX_CARD_QUERIES.upstreamTime, phases);
  const tablePhase = phaseOf(NGINX_CARD_QUERIES.upstreamTable, phases);
  const failures = [kpiPhase, kpiPhase, kpiPhase, kpiPhase, trendPhase, timePhase, timePhase, statusPhase, statusPhase, tablePhase]
    .filter((item) => item === 'error').length;
  const timeText = (value: number | null) => textOf(value, formatDuration(value ?? 0, model.upstreamTimeUnit));
  const memberMetric = (member: UpstreamMemberRow, key: string) => {
    if (key === 'weight') return member.weight;
    if (key === 'rate') return member.requestRate;
    if (key === 'window') return member.windowRequests ?? null;
    if (key === '4xx') return member.windowCodes?.['4xx'] ?? null;
    if (key === '5xx') return member.windowCodes?.['5xx'] ?? null;
    if (key === 'in') return member.windowBytesIn ?? null;
    if (key === 'out') return member.windowBytesOut ?? null;
    if (key === 'request') return member.requestMs;
    if (key === 'response') return member.responseMs;
    if (key === 'maxFails') return member.maxFails;
    if (key === 'failTimeout') return member.failTimeout;
    return null;
  };
  const groupMetric = (group: UpstreamGroupRow, key: string) => {
    if (key === 'rate') return group.requestRate;
    if (key === 'window') return group.windowRequests ?? null;
    if (key === '4xx') return group.windowCodes?.['4xx'] ?? null;
    if (key === '5xx') return group.windowCodes?.['5xx'] ?? null;
    return null;
  };
  const groups = useMemo(() => {
    const visible = model.upstreamGroups
      .map((group) => ({
        ...group,
        members: downOnly ? group.members.filter((member) => member.down === 1) : group.members
      }))
      .filter((group) => !downOnly || group.members.length > 0);
    const compare = (left: number | null, right: number | null) => {
      const delta = (right ?? Number.NEGATIVE_INFINITY) - (left ?? Number.NEGATIVE_INFINITY);
      return sortDesc ? delta : -delta;
    };
    return [...visible]
      .sort((left, right) => {
        if (!sortKey || groupMetric(left, sortKey) == null && groupMetric(right, sortKey) == null) {
          return left.upstream.localeCompare(right.upstream, 'zh');
        }
        return compare(groupMetric(left, sortKey), groupMetric(right, sortKey))
          || left.upstream.localeCompare(right.upstream, 'zh');
      })
      .map((group) => ({
        ...group,
        members: sortKey ? [...group.members].sort((left, right) => (
          compare(memberMetric(left, sortKey), memberMetric(right, sortKey))
        )) : group.members
      }));
  }, [downOnly, model.upstreamGroups, sortDesc, sortKey]);
  const chooseSort = (key: string) => {
    if (sortKey === key) setSortDesc((value) => !value);
    else {
      setSortKey(key);
      setSortDesc(true);
    }
  };
  const memberCsv = (member: UpstreamMemberRow) => {
    const state = memberState(member);
    const address = member.addressLabel || member.address;
    return [
      state.label,
      address,
      textOf(member.weight, formatPlain(member.weight ?? 0)),
      textOf(member.requestRate, formatPerSecond(member.requestRate ?? 0, '次')),
      textOf(member.windowRequests ?? null, formatCount(member.windowRequests ?? 0, '次')),
      textOf(member.windowCodes?.['4xx'] ?? null, formatCount(member.windowCodes?.['4xx'] ?? 0, '次')),
      textOf(member.windowCodes?.['5xx'] ?? null, formatCount(member.windowCodes?.['5xx'] ?? 0, '次')),
      textOf(member.windowBytesIn ?? null, formatBytes(member.windowBytesIn ?? 0)),
      textOf(member.windowBytesOut ?? null, formatBytes(member.windowBytesOut ?? 0)),
      timeText(member.requestMs),
      timeText(member.responseMs),
      textOf(member.maxFails, formatPlain(member.maxFails ?? 0, '次')),
      textOf(member.failTimeout, formatPlain(member.failTimeout ?? 0, '秒'))
    ];
  };
  const groupCsv = (group: UpstreamGroupRow) => [
    '',
    `${group.upstream} ${group.members.length} 个成员`,
    '',
    textOf(group.requestRate, formatPerSecond(group.requestRate ?? 0, '次')),
    textOf(group.windowRequests ?? null, formatCount(group.windowRequests ?? 0, '次')),
    textOf(group.windowCodes?.['4xx'] ?? null, formatCount(group.windowCodes?.['4xx'] ?? 0, '次')),
    textOf(group.windowCodes?.['5xx'] ?? null, formatCount(group.windowCodes?.['5xx'] ?? 0, '次')),
    '',
    '',
    '',
    '',
    '',
    ''
  ];
  const renderCells = (csv: readonly string[], addressTitle?: string): ReactNode[] => csv.map((value, index) => {
    if (index === 0 && value) {
      const className = value === '已下线'
        ? 'bg-[color-mix(in_srgb,var(--color-fail)_14%,transparent)] text-[var(--color-fail)]'
        : value === '备份'
          ? 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]'
          : 'bg-[color-mix(in_srgb,var(--color-success)_14%,transparent)] text-[var(--color-success)]';
      return <span key={value} className={`inline-flex rounded-full px-2 py-0.5 text-[12px] ${className}`}>{value}</span>;
    }
    if (index === 1) {
      return <span key={value} className="block max-w-[220px] truncate" title={addressTitle || value}>{value}</span>;
    }
    return value;
  });
  const tableRows: ProMetricRow[] = groups.flatMap((group) => {
    const summary = groupCsv(group);
    const head: ProMetricRow = {
      key: `group:${group.upstream}`,
      variant: 'group',
      csv: summary,
      cells: renderCells(summary, group.upstream)
    };
    const members = group.members.map((member) => {
      const csv = memberCsv(member);
      const address = member.addressLabel || member.address;
      return {
        key: `${member.upstream}|${address}`,
        csv,
        cells: renderCells(csv, address)
      };
    });
    return [head, ...members];
  });
  const statusBlocked = board.up5xx === '暂无数据';
  const statusParts = STATUS_ORDER.map((code) => ({
    id: code,
    label: code,
    color: STATUS_COLORS[code],
    value: statusBlocked ? null : (board.upstreamStatusParts.find((part) => part.code === code)?.count ?? 0)
  }));

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="upstream">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className={CELL} data-nginx-width="1/4">
          <NginxTile label="上游请求速率" hint={NGINX_HINTS.upRate} unit="次/秒" figure={board.upRate} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)} />
        </div>
        <div className={CELL} data-nginx-width="1/4">
          <NginxTile
            label="上游 5xx 次数"
            hint={NGINX_HINTS.up5xx}
            unit="次"
            figure={board.up5xx}
            sub={board.up5xxSub}
            tone={board.up5xxHot ? 'var(--color-fail)' : undefined}
            phase={kpiPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)}
          />
        </div>
        <div className={CELL} data-nginx-width="1/4">
          <NginxTile label="平均响应时间" hint={NGINX_HINTS.upTime} unit={durationUnitLabel(board.upTimeUnit)} figure={board.upTime} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)} />
        </div>
        <div className={CELL} data-nginx-width="1/4">
          <NginxTile
            label="在线成员"
            hint={NGINX_HINTS.upOnline}
            figure={board.upOnline}
            phase={kpiPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)}
            extra={board.upDown > 0 ? <span className="rounded-full bg-[color-mix(in_srgb,var(--color-fail)_14%,transparent)] px-2 py-0.5 text-[12px] text-[var(--color-fail)]">已下线 {board.upDown}</span> : null}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className={THIRD} data-nginx-width="1/3">
          <NginxChartCard
            title="上游请求速率"
            hint={NGINX_HINTS.upRate}
            unit="次/秒"
            items={board.upstreamGroupTrend}
            floor={1}
            formatReading={(value) => formatPerSecond(value, '次')}
            phase={trendPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamTrend)}
          />
        </div>
        <div className={THIRD} data-nginx-width="1/3">
          <NginxChartCard
            title="响应时间"
            hint={NGINX_HINTS.upResponse}
            unit={durationUnitLabel(model.upstreamTimeUnit)}
            items={topSeries(model.upstreamResponseTime)}
            floor={10}
            formatReading={(value) => formatDuration(value, model.upstreamTimeUnit)}
            phase={timePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamTime)}
          />
        </div>
        <div className={THIRD} data-nginx-width="1/3">
          <NginxChartCard
            title="请求处理时间"
            hint={NGINX_HINTS.upRequestTime}
            unit={durationUnitLabel(model.upstreamTimeUnit)}
            items={topSeries(model.upstreamRequestTime)}
            floor={10}
            formatReading={(value) => formatDuration(value, model.upstreamTimeUnit)}
            phase={timePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamTime)}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <div data-nginx-width="1/2">
          <NginxChartCard
            title="上游状态码分布"
            hint={NGINX_HINTS.upStatus}
            unit="次"
            items={statusBlocked ? [] : board.upstreamStatusSteps}
            floor={1}
            kind="bar"
            countAxis
            formatReading={(value) => formatCount(value, '次')}
            phase={statusPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamStatus)}
          />
        </div>
        <div data-nginx-width="1/2">
          <NginxCompositionCard
            title="上游状态码构成"
            hint={NGINX_HINTS.upStatusMix}
            parts={statusParts}
            noun="次"
            phase={statusPhase}
            emptyText={board.up5xxSub || emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamStatus)}
          />
        </div>
      </div>
      <ProMetricTable
        id="nginx-upstream-table"
        title="上游"
        hint={<NginxHint copy={NGINX_HINTS.upstream} />}
        extra={model.upstreamDownOnly ? (
          <label className="inline-flex items-center gap-2 text-[13px] text-[var(--color-text-1)]">
            仅看已下线
            <Switch size="small" checked={downOnly} onChange={setDownOnly} />
          </label>
        ) : null}
        objectName="nginx"
        tabName="上游"
        tableName="上游"
        columns={columns}
        rows={tablePhase === 'ready' ? tableRows : []}
        heightClass="h-[360px]"
        onSort={chooseSort}
        empty={tablePhase !== 'ready' ? (
          <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={tablePhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamTable)} height={300} />
        ) : tableRows.length ? undefined : (
          <div className="flex flex-1 items-center justify-center text-[14px] text-[var(--color-text-3)]">{emptyText}</div>
        )}
      />
    </div>
  );
}
