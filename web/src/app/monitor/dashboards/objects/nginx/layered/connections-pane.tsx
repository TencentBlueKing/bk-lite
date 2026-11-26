'use client';

import { formatCount, formatDecimal, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxCompositionCard, type NginxPiePart } from './nginx-composition';
import type { NginxDashboardModel } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';

const SHARE_COLORS = [
  { id: 'reading', label: '读取', color: '#27c274' },
  { id: 'writing', label: '写入', color: '#ff8a1f' },
  { id: 'waiting', label: '等待', color: '#8a5cff' }
] as const;

const CELL = 'flex min-w-0 min-[1100px]:col-span-3';

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
  const { active, reading, writing, waiting } = model.ring;
  const parts: NginxPiePart[] = [
    { ...SHARE_COLORS[0], value: reading },
    { ...SHARE_COLORS[1], value: writing },
    { ...SHARE_COLORS[2], value: waiting }
  ];
  const activeKnown = active != null;
  return (
    <div className="flex flex-col gap-4" data-nginx-pane="connections">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        {([
          ['reading', '读取连接', NGINX_HINTS.reading, board.readingFigure],
          ['writing', '写入连接', NGINX_HINTS.writing, board.writingFigure],
          ['waiting', '等待连接', NGINX_HINTS.waiting, board.waitingFigure]
        ] as const).map(([key, label, hint, figure]) => (
          <div key={key} className={CELL} data-nginx-width="1/4">
            <NginxTile
              label={label}
              hint={hint}
              unit="个"
              figure={figure}
              phase={gaugePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
            />
          </div>
        ))}
        <div className={CELL} data-nginx-width="1/4">
          <NginxTile
            label="繁忙连接"
            hint={NGINX_HINTS.busy}
            unit="个"
            figure={board.busyFigure}
            phase={gaugePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <div data-nginx-width="1/2">
          <NginxCompositionCard
            anchor="nginx-conn-mix"
            title="连接构成"
            hint={NGINX_HINTS.composition}
            parts={parts}
            noun="个"
            headline={activeKnown ? `活跃连接 ${formatCount(active ?? 0, '')}` : undefined}
            idleText={active === 0 ? '当前没有活跃连接' : undefined}
            phase={gaugePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
          />
        </div>
        <div data-nginx-width="1/2">
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
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <div data-nginx-width="1/2">
          <NginxChartCard
            title="连接数"
            hint={NGINX_HINTS.states}
            unit="个"
            items={model.connSeries}
            floor={1}
            kind="step"
            countAxis
            formatReading={(value) => formatCount(value, '个')}
            phase={gaugePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.connections)}
          />
        </div>
        <div data-nginx-width="1/2">
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
    </div>
  );
}
