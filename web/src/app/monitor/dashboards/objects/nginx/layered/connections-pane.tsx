'use client';

import { formatCount, formatDecimal, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxHint } from './nginx-hint';
import type { NginxDashboardModel } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';

const SHARE_COLORS = [
  { id: 'reading', label: '读取', color: '#27c274' },
  { id: 'writing', label: '写入', color: '#ff8a1f' },
  { id: 'waiting', label: '等待', color: '#8a5cff' }
] as const;

function ConnectionMix({ model, phase, emptyText, onRetry }: {
  model: NginxDashboardModel;
  phase: NginxQueryPhase;
  emptyText: string;
  onRetry: () => void;
}) {
  const { active, reading, writing, waiting } = model.ring;
  const parts = [
    { ...SHARE_COLORS[0], value: reading },
    { ...SHARE_COLORS[1], value: writing },
    { ...SHARE_COLORS[2], value: waiting }
  ];
  const known = active != null && parts.every((part) => part.value != null);
  if (phase !== 'ready' || !known) {
    return (
      <NginxChartCard
        anchor="nginx-conn-mix"
        title="连接构成"
        hint={NGINX_HINTS.composition}
        items={[]}
        floor={1}
        formatReading={(value) => formatCount(value, '个')}
        phase={phase === 'ready' ? 'ready' : phase}
        emptyText={emptyText}
        onRetry={onRetry}
      />
    );
  }
  const sum = parts.reduce((total, part) => total + Math.max(part.value ?? 0, 0), 0);
  const idle = active === 0;
  return (
    <section id="nginx-conn-mix" className="flex h-[280px] flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-3" data-nginx-mix="">
      <div className="inline-flex items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
        连接构成
        <NginxHint copy={NGINX_HINTS.composition} />
      </div>
      <div className="mt-3 text-[13px] text-[var(--color-text-2)]">活跃连接 {formatCount(active ?? 0, '')}</div>
      <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]">
        {idle ? null : (
          <div className="flex h-full w-full">
            {parts.map((part) => (
              <div key={part.id} style={{ width: `${sum === 0 ? 0 : ((part.value ?? 0) / sum) * 100}%`, background: part.color }} />
            ))}
          </div>
        )}
      </div>
      {idle ? <div className="mt-3 text-[14px] text-[var(--color-text-3)]">当前没有活跃连接</div> : null}
      <div className="mt-3 flex flex-col gap-2 text-[13px] text-[var(--color-text-1)]">
        {parts.map((part) => {
          const value = part.value ?? 0;
          const share = sum === 0 ? 0 : (value / sum) * 100;
          return (
            <div key={part.id} className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: part.color }} />
                {part.label}
              </span>
              <span className="tabular-nums">{formatCount(value, '个')} · {formatDecimal(share)}%</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function ConnectionsPane({
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
  const board = model.board;
  const gaugePhase = phaseOf(NGINX_CARD_QUERIES.connections, phases);
  const dropPhase = phaseOf(NGINX_CARD_QUERIES.dropped, phases);
  const failures = [gaugePhase, gaugePhase, gaugePhase, gaugePhase, gaugePhase, gaugePhase, gaugePhase, dropPhase]
    .filter((item) => item === 'error').length;
  const percentText = (value: number) => `${formatDecimal(value)}%`;
  return (
    <div className="flex flex-col gap-4" data-nginx-pane="connections">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        {([
          ['reading', '读取连接', NGINX_HINTS.reading, board.readingFigure, model.connSeries.find((item) => item.id === 'reading')?.points],
          ['writing', '写入连接', NGINX_HINTS.writing, board.writingFigure, model.connSeries.find((item) => item.id === 'writing')?.points],
          ['waiting', '等待连接', NGINX_HINTS.waiting, board.waitingFigure, model.connSeries.find((item) => item.id === 'waiting')?.points]
        ] as const).map(([key, label, hint, figure, points]) => (
          <div key={key} className="min-[1100px]:col-span-3">
            <NginxTile
              label={label}
              hint={hint}
              figure={figure}
              spark={points}
              sparkStep
              phase={gaugePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
            />
          </div>
        ))}
        <div className="min-[1100px]:col-span-3">
          <NginxTile
            label="繁忙连接占比"
            hint={NGINX_HINTS.busy}
            figure={board.busyFigure}
            progress={board.busyShare}
            phase={gaugePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <ConnectionMix
          model={model}
          phase={gaugePhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
        />
        <NginxChartCard
          title="连接占比趋势"
          hint={NGINX_HINTS.ratioTrend}
          unit="%"
          items={[
            { id: 'busy', label: '繁忙占比', color: '#ff8a1f', points: model.busyPoints, reading: '' },
            { id: 'waiting', label: '等待占比', color: '#8a5cff', points: model.waitingPoints, reading: '' }
          ]}
          floor={1}
          percent
          formatReading={percentText}
          phase={gaugePhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <NginxChartCard
          title="连接数"
          hint={NGINX_HINTS.states}
          unit="个"
          items={model.connSeries}
          floor={1}
          kind="step"
          formatReading={(value) => formatCount(value, '个')}
          phase={gaugePhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
        />
        <NginxChartCard
          anchor="nginx-dropped"
          title="丢弃连接速率"
          hint={NGINX_HINTS.dropped}
          unit="连接/秒"
          items={[{ id: 'dropped', label: '丢弃连接速率', color: '#ff7875', points: model.droppedPoints, reading: '' }]}
          floor={1}
          formatReading={(value) => formatPerSecond(value, '连接')}
          phase={dropPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.dropped)}
        />
      </div>
    </div>
  );
}
