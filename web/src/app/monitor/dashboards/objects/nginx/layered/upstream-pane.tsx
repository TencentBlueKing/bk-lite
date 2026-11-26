'use client';

import { Fragment, useState } from 'react';
import { Switch } from 'antd';
import { durationUnitLabel, formatBytes, formatCount, formatDuration, formatPerSecond, formatPlain } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxHint } from './nginx-hint';
import type { NginxDashboardModel, NginxSeriesItem, UpstreamGroupRow, UpstreamMemberRow } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';

const topSeries = (items: readonly NginxSeriesItem[]) => [...items]
  .sort((left, right) => (right.points[right.points.length - 1]?.value ?? 0) - (left.points[left.points.length - 1]?.value ?? 0))
  .slice(0, 5);

const cell = (value: number | null | undefined, text: string) => (value == null ? '--' : text);

const memberState = (member: UpstreamMemberRow) => {
  if (member.down === 1) return { label: '已下线', className: 'bg-[color-mix(in_srgb,var(--color-fail)_14%,transparent)] text-[var(--color-fail)]' };
  if (member.backup === 1) return { label: '备份', className: 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]' };
  return { label: '在线', className: 'bg-[color-mix(in_srgb,var(--color-success)_14%,transparent)] text-[var(--color-success)]' };
};

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
  const board = model.board;
  const kpiPhase = phaseOf(NGINX_CARD_QUERIES.upstreamKpi, phases);
  const trendPhase = phaseOf(NGINX_CARD_QUERIES.upstreamTrend, phases);
  const statusPhase = phaseOf(NGINX_CARD_QUERIES.upstreamStatus, phases);
  const timePhase = phaseOf(NGINX_CARD_QUERIES.upstreamTime, phases);
  const tablePhase = phaseOf(NGINX_CARD_QUERIES.upstreamTable, phases);
  const failures = [kpiPhase, kpiPhase, kpiPhase, kpiPhase, trendPhase, statusPhase, timePhase, timePhase, tablePhase]
    .filter((item) => item === 'error').length;
  const groups = model.upstreamGroups
    .map((group) => ({
      ...group,
      members: downOnly ? group.members.filter((member) => member.down === 1) : group.members
    }))
    .filter((group) => !downOnly || group.members.length > 0);
  const timeText = (value: number | null) => cell(value, formatDuration(value ?? 0, model.upstreamTimeUnit));
  const renderMember = (member: UpstreamMemberRow) => {
    const state = memberState(member);
    const address = member.addressLabel || member.address;
    return (
      <tr key={`${member.upstream}|${member.address}|${address}`} data-nginx-upstream-member={address}>
        <td className="px-2 py-2">
          <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] ${state.className}`}>{state.label}</span>
        </td>
        <td className="max-w-[220px] truncate px-2 py-2" title={address}>{address}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.weight, formatPlain(member.weight ?? 0))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.requestRate, formatPerSecond(member.requestRate ?? 0, '次'))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.windowRequests ?? null, formatCount(member.windowRequests ?? 0, '次'))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.windowCodes?.['4xx'] ?? null, formatCount(member.windowCodes?.['4xx'] ?? 0, '次'))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.windowCodes?.['5xx'] ?? null, formatCount(member.windowCodes?.['5xx'] ?? 0, '次'))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.windowBytesIn ?? null, formatBytes(member.windowBytesIn ?? 0))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.windowBytesOut ?? null, formatBytes(member.windowBytesOut ?? 0))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{timeText(member.requestMs)}</td>
        <td className="px-2 py-2 text-right tabular-nums">{timeText(member.responseMs)}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.maxFails, formatPlain(member.maxFails ?? 0, '次'))}</td>
        <td className="px-2 py-2 text-right tabular-nums">{cell(member.failTimeout, formatPlain(member.failTimeout ?? 0, '秒'))}</td>
      </tr>
    );
  };
  const groupCells = (group: UpstreamGroupRow) => (
    <>
      <td />
      <td className="px-2 py-2 font-semibold">{group.upstream}<span className="ml-2 font-normal text-[var(--color-text-3)]">{group.members.length} 个成员</span></td>
      <td />
      <td className="px-2 py-2 text-right tabular-nums">{cell(group.requestRate, formatPerSecond(group.requestRate ?? 0, '次'))}</td>
      <td className="px-2 py-2 text-right tabular-nums">{cell(group.windowRequests ?? null, formatCount(group.windowRequests ?? 0, '次'))}</td>
      <td className="px-2 py-2 text-right tabular-nums">{cell(group.windowCodes?.['4xx'] ?? null, formatCount(group.windowCodes?.['4xx'] ?? 0, '次'))}</td>
      <td className="px-2 py-2 text-right tabular-nums">{cell(group.windowCodes?.['5xx'] ?? null, formatCount(group.windowCodes?.['5xx'] ?? 0, '次'))}</td>
      <td /><td /><td /><td /><td /><td />
    </>
  );

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="upstream">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="上游请求速率" hint={NGINX_HINTS.upRate} unit="次/秒" figure={board.upRate} spark={board.upstreamGroupTrend[0]?.points} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="上游 5xx 比例" hint={NGINX_HINTS.up5xx} figure={board.up5xx} sub={board.up5xxSub} tone={board.up5xx !== '暂无数据' && board.up5xx !== '0.0%' ? 'var(--color-fail)' : undefined} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="平均响应时间" hint={NGINX_HINTS.upTime} figure={board.upTime} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
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
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
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
        <NginxChartCard
          title="上游状态码分布"
          hint={NGINX_HINTS.upStatus}
          unit="次"
          items={board.upstreamStatusSteps}
          floor={1}
          kind="bar"
          formatReading={(value) => formatCount(value, '次')}
          phase={statusPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamStatus)}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
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
      <section id="nginx-upstream-table" className="flex h-[360px] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]" data-nginx-upstream-table="">
        <div className="flex items-center justify-between gap-3 px-3 pt-3">
          <div className="inline-flex items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
            上游
            <NginxHint copy={NGINX_HINTS.upstream} />
          </div>
          {model.upstreamDownOnly ? (
            <label className="inline-flex items-center gap-2 text-[13px] text-[var(--color-text-1)]">
              仅看已下线
              <Switch size="small" checked={downOnly} onChange={setDownOnly} />
            </label>
          ) : null}
        </div>
        {tablePhase !== 'ready' ? (
          <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={tablePhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.upstreamTable)} height={300} />
        ) : (
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 bg-[var(--color-bg)] text-right text-[var(--color-text-2)]">
                <tr>
                  <th className="px-2 py-2 text-left">状态</th>
                  <th className="min-w-[160px] px-2 py-2 text-left">地址</th>
                  <th className="px-2 py-2">权重</th>
                  <th className="px-2 py-2">请求速率</th>
                  <th className="px-2 py-2">窗口请求数</th>
                  <th className="px-2 py-2">4xx</th>
                  <th className="px-2 py-2">5xx</th>
                  <th className="px-2 py-2">入站</th>
                  <th className="px-2 py-2">出站</th>
                  <th className="px-2 py-2">请求处理时间</th>
                  <th className="px-2 py-2">响应时间</th>
                  <th className="px-2 py-2">最大失败次数</th>
                  <th className="px-2 py-2">失败暂停时长</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <Fragment key={group.upstream}>
                    <tr className="bg-[var(--color-fill-1)]" data-nginx-upstream-group={group.upstream}>
                      {groupCells(group)}
                    </tr>
                    {group.members.map((member) => renderMember(member))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
