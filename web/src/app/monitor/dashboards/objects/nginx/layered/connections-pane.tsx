'use client';

import { ProSection } from '../../host/layered/pro-chrome';
import { formatCount, formatPercent, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxDimensionalChart } from './dimensional-chart';
import type { NginxDashboardModel } from './model';
import { NginxHint } from './nginx-hint';

function ConnectionRing({ ring }: { ring: NginxDashboardModel['ring'] }) {
  const { active, reading, writing, waiting } = ring;
  if (active == null || reading == null || writing == null || waiting == null) {
    return <div className="flex h-full min-h-[180px] items-center justify-center text-[13px] font-semibold text-[var(--color-text-2)]">暂无数据</div>;
  }
  const parts = [
    { label: '读取', value: reading, color: '#27c274' },
    { label: '写入', value: writing, color: '#ff8a1f' },
    { label: '等待', value: waiting, color: '#8a5cff' }
  ];
  const sum = parts.reduce((total, part) => total + Math.max(part.value, 0), 0);
  let cursor = 0;
  const stops = sum === 0
    ? 'var(--color-fill-2) 0 100%'
    : parts.map((part) => {
      const start = cursor;
      cursor += (part.value / sum) * 100;
      return `${part.color} ${start}% ${cursor}%`;
    }).join(', ');
  return (
    <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-3 p-4" data-nginx-ring="">
      <div
        className="relative h-36 w-36 rounded-full"
        style={{ background: `conic-gradient(${stops})` }}
      >
        <div className="absolute inset-4 flex flex-col items-center justify-center rounded-full bg-[var(--color-bg)]">
          <div className="text-[22px] font-semibold tabular-nums text-[var(--color-text-1)]">{formatCount(active, '')}</div>
          <div className="text-[12px] text-[var(--color-text-3)]">活跃连接</div>
        </div>
      </div>
      <div className="flex flex-wrap justify-center gap-3 text-[12px] text-[var(--color-text-2)]">
        {parts.map((part) => (
          <span key={part.label} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: part.color }} />
            {part.label} {formatCount(part.value, '个')}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ConnectionsPane({
  model,
  loading,
  emptyText
}: {
  model: NginxDashboardModel;
  loading: boolean;
  emptyText: string;
}) {
  const dropped = [{
    id: 'dropped',
    label: '丢弃连接速率',
    color: '#ff7875',
    points: model.droppedPoints,
    reading: model.dropped
  }];
  const busy = [{
    id: 'busy',
    label: '繁忙占比',
    color: '#ff8a1f',
    points: model.busyPoints,
    reading: model.busy
  }];
  const waiting = [{
    id: 'waiting',
    label: '等待占比',
    color: '#8a5cff',
    points: model.waitingPoints,
    reading: model.waiting
  }];
  return (
    <div className="flex flex-col gap-4" data-nginx-pane="connections">
      <ProSection title="连接四态" hint={<NginxHint copy={NGINX_HINTS.states} />}>
        <NginxDimensionalChart
          title="连接四态"
          hint={NGINX_HINTS.states}
          items={model.connSeries}
          floor={1}
          formatReading={(value) => formatCount(value, '个')}
          loading={loading}
          emptyText={emptyText}
        />
      </ProSection>
      <div className="grid grid-cols-1 gap-3 min-[1100px]:grid-cols-2">
        <NginxDimensionalChart
          title="接受速率与处理速率"
          hint={NGINX_HINTS.acceptHandled}
          items={[
            { id: 'accepts', label: '接受速率', color: '#13c2c2', points: model.acceptPoints, reading: model.accepts },
            { id: 'handled', label: '处理速率', color: '#597ef7', points: model.handledPoints, reading: model.handledRate }
          ]}
          floor={1}
          formatReading={(value) => formatPerSecond(value, '连接')}
          loading={loading}
          emptyText={emptyText}
        />
        <NginxDimensionalChart
          title="丢弃连接速率"
          hint={NGINX_HINTS.dropped}
          items={dropped}
          floor={1}
          formatReading={(value) => formatPerSecond(value, '连接')}
          loading={loading}
          emptyText={emptyText}
        />
        <NginxDimensionalChart
          title="繁忙连接占比"
          hint={NGINX_HINTS.busy}
          items={busy}
          floor={1}
          formatReading={(value) => formatPercent(value / 100)}
          loading={loading}
          emptyText={emptyText}
        />
        <NginxDimensionalChart
          title="等待连接占比"
          hint={NGINX_HINTS.waiting}
          items={waiting}
          floor={1}
          formatReading={(value) => formatPercent(value / 100)}
          loading={loading}
          emptyText={emptyText}
        />
      </div>
      <ProSection title="连接现状" hint={<NginxHint copy={NGINX_HINTS.ring} />}>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
          {loading ? <div className="min-h-[180px]" /> : <ConnectionRing ring={model.ring} />}
        </div>
        {model.requestTotal ? (
          <p className="m-0 text-[12px] text-[var(--color-text-3)]">
            累计请求 {model.requestTotal}
            <span className="ml-1 inline-flex align-middle"><NginxHint copy={NGINX_HINTS.total} /></span>
          </p>
        ) : null}
      </ProSection>
    </div>
  );
}
