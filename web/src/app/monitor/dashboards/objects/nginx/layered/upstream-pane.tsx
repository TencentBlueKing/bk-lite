'use client';

import { useState } from 'react';
import { ProSection } from '../../host/layered/pro-chrome';
import { formatBytesPerSecond, formatDuration, formatPerSecond, formatPlain } from './format';
import { NGINX_HINTS } from './hints';
import { NginxDimensionalChart } from './dimensional-chart';
import { NginxHint } from './nginx-hint';
import { upstreamColumns, type NginxDashboardModel, type UpstreamMemberRow } from './model';

const cell = (value: number | null, text: string) => (value == null ? '--' : text);

const flagText = (value: number | null, on: string, off: string) => {
  if (value == null) return '--';
  return value === 1 ? on : off;
};

export default function UpstreamPane({
  model,
  loading,
  emptyText
}: {
  model: NginxDashboardModel;
  loading: boolean;
  emptyText: string;
}) {
  const [downOnly, setDownOnly] = useState(false);
  const scale = { div: model.byteScaleDiv, suffix: model.byteSuffix };
  const columns = upstreamColumns(model.upstreamGroups);
  const tableColSpan = 2 + Object.values(columns).filter(Boolean).length;
  const groups = model.upstreamGroups
    .map((group) => ({
      ...group,
      members: downOnly ? group.members.filter((member) => member.down === 1) : group.members
    }))
    .filter((group) => !downOnly || group.members.length > 0);
  const rateText = (value: number | null) => cell(value, formatPerSecond(value ?? 0, '次'));
  const byteText = (value: number | null) => cell(value, formatBytesPerSecond(value ?? 0, scale));
  const timeText = (value: number | null) => cell(value, formatDuration(value ?? 0, model.upstreamTimeUnit));
  const memberCells = (member: UpstreamMemberRow) => (
    <>
      {columns.request ? <td className="px-2 py-2 tabular-nums">{rateText(member.requestRate)}</td> : null}
      {columns.c4 ? <td className="px-2 py-2 tabular-nums">{rateText(member.codes['4xx'])}</td> : null}
      {columns.c5 ? <td className="px-2 py-2 tabular-nums">{rateText(member.codes['5xx'])}</td> : null}
      {columns.bytesIn ? <td className="px-2 py-2 tabular-nums">{byteText(member.bytesIn)}</td> : null}
      {columns.bytesOut ? <td className="px-2 py-2 tabular-nums">{byteText(member.bytesOut)}</td> : null}
      {columns.requestMs ? <td className="px-2 py-2 tabular-nums">{timeText(member.requestMs)}</td> : null}
      {columns.responseMs ? <td className="px-2 py-2 tabular-nums">{timeText(member.responseMs)}</td> : null}
      {columns.down ? <td className="px-2 py-2">{flagText(member.down, '已下线', '在线')}</td> : null}
      {columns.backup ? <td className="px-2 py-2">{flagText(member.backup, '备份', '否')}</td> : null}
      {columns.weight ? <td className="px-2 py-2 tabular-nums">{cell(member.weight, formatPlain(member.weight ?? 0))}</td> : null}
      {columns.maxFails ? <td className="px-2 py-2 tabular-nums">{cell(member.maxFails, formatPlain(member.maxFails ?? 0, '次'))}</td> : null}
      {columns.failTimeout ? <td className="px-2 py-2 tabular-nums">{cell(member.failTimeout, formatPlain(member.failTimeout ?? 0, '秒'))}</td> : null}
    </>
  );

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="upstream">
      <NginxDimensionalChart
        title="上游请求速率"
        hint={NGINX_HINTS.request}
        items={model.upstreamRequest}
        floor={1}
        formatReading={(value) => formatPerSecond(value, '次')}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="请求处理时间"
        hint={NGINX_HINTS.upstreamTime}
        items={model.upstreamRequestTime}
        floor={10}
        formatReading={(value) => formatDuration(value, model.upstreamTimeUnit)}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="响应时间"
        hint={NGINX_HINTS.upstreamTime}
        items={model.upstreamResponseTime}
        floor={10}
        formatReading={(value) => formatDuration(value, model.upstreamTimeUnit)}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="状态码"
        hint={NGINX_HINTS.codes}
        items={model.upstreamStatus}
        floor={1}
        stack
        formatReading={(value) => formatPerSecond(value, '次')}
        loading={loading}
        emptyText={emptyText}
      />
      <ProSection title="上游" hint={<NginxHint copy={NGINX_HINTS.upstreamDown} />}>
        {model.upstreamDownOnly ? (
          <label className="mb-2 inline-flex items-center gap-2 text-[13px] text-[var(--color-text-1)]">
            <input type="checkbox" checked={downOnly} onChange={(event) => setDownOnly(event.target.checked)} />
            仅看已下线
          </label>
        ) : null}
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-3)]">
                <th className="px-2 py-2 font-semibold">上游</th>
                <th className="px-2 py-2 font-semibold">地址</th>
                {columns.request ? <th className="px-2 py-2 font-semibold">请求速率</th> : null}
                {columns.c4 ? <th className="px-2 py-2 font-semibold">4xx</th> : null}
                {columns.c5 ? <th className="px-2 py-2 font-semibold">5xx</th> : null}
                {columns.bytesIn ? <th className="px-2 py-2 font-semibold">入站速率</th> : null}
                {columns.bytesOut ? <th className="px-2 py-2 font-semibold">出站速率</th> : null}
                {columns.requestMs ? <th className="px-2 py-2 font-semibold">请求时间</th> : null}
                {columns.responseMs ? <th className="px-2 py-2 font-semibold">响应时间</th> : null}
                {columns.down ? <th className="px-2 py-2 font-semibold">下线标记</th> : null}
                {columns.backup ? <th className="px-2 py-2 font-semibold">备份标记</th> : null}
                {columns.weight ? <th className="px-2 py-2 font-semibold">权重</th> : null}
                {columns.maxFails ? <th className="px-2 py-2 font-semibold">最大失败次数</th> : null}
                {columns.failTimeout ? <th className="px-2 py-2 font-semibold">失败暂停时长</th> : null}
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.upstream || 'group'} data-nginx-upstream-group={group.upstream}>
                <tr className="bg-[var(--color-fill-1)]">
                  <td className="px-2 py-2 font-semibold text-[var(--color-text-1)]">{group.upstream || '--'}</td>
                  <td className="px-2 py-2 text-[var(--color-text-3)]">--</td>
                  {columns.request ? <td className="px-2 py-2 tabular-nums">{rateText(group.requestRate)}</td> : null}
                  {columns.c4 ? <td className="px-2 py-2 tabular-nums">{rateText(group.codes['4xx'])}</td> : null}
                  {columns.c5 ? <td className="px-2 py-2 tabular-nums">{rateText(group.codes['5xx'])}</td> : null}
                  {columns.bytesIn ? <td className="px-2 py-2 tabular-nums">{byteText(group.bytesIn)}</td> : null}
                  {columns.bytesOut ? <td className="px-2 py-2 tabular-nums">{byteText(group.bytesOut)}</td> : null}
                  {columns.requestMs ? <td className="px-2 py-2">--</td> : null}
                  {columns.responseMs ? <td className="px-2 py-2">--</td> : null}
                  {columns.down ? <td className="px-2 py-2">--</td> : null}
                  {columns.backup ? <td className="px-2 py-2">--</td> : null}
                  {columns.weight ? <td className="px-2 py-2">--</td> : null}
                  {columns.maxFails ? <td className="px-2 py-2">--</td> : null}
                  {columns.failTimeout ? <td className="px-2 py-2">--</td> : null}
                </tr>
                {group.members.map((member) => (
                  <tr key={`${member.upstream}|${member.address}`}>
                    <td className="px-2 py-2 text-[var(--color-text-3)]">{member.upstream}</td>
                    <td className="px-2 py-2">{member.address || '--'}</td>
                    {memberCells(member)}
                  </tr>
                ))}
              </tbody>
            ))}
            {!groups.length ? (
              <tbody>
                <tr>
                  <td className="px-2 py-6 text-center font-semibold text-[var(--color-text-2)]" colSpan={tableColSpan}>{emptyText}</td>
                </tr>
              </tbody>
            ) : null}
          </table>
        </div>
      </ProSection>
    </div>
  );
}
