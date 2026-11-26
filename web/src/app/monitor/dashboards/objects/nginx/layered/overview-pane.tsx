'use client';

import { useLinkedHost } from '../../../shared/use-linked-host';
import { LinkedHostSegment } from '../../../shared/widgets/linked-host-segment';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { formatCount, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxFocusTile, NginxRetryBanner, NginxTile } from './nginx-card';
import type { NginxDashboardModel } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';

export type NginxTabKey = 'overview' | 'connections' | 'sites' | 'upstream';

const rateText = (value: number) => formatPerSecond(value, '次');
const connText = (value: number) => formatPerSecond(value, '连接');

export default function OverviewPane({
  model,
  phases,
  alertPhase,
  emptyText,
  alertCount,
  alertEvents,
  nodeId,
  ip,
  onOpenAlerts,
  onFocusAlert,
  onOpen,
  onRetry,
  onRetryFailed,
  onRetryAlerts
}: {
  model: NginxDashboardModel;
  phases: Readonly<Record<string, NginxQueryPhase>>;
  alertPhase: NginxQueryPhase;
  emptyText: string;
  alertCount: number | null;
  alertEvents: HostAlertRailEvent[];
  nodeId: string;
  ip: string;
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpen: (tab: NginxTabKey, anchor?: string) => void;
  onRetry: (keys: readonly string[]) => void;
  onRetryFailed: () => void;
  onRetryAlerts: () => void;
}) {
  const linked = useLinkedHost(nodeId, ip, Boolean(nodeId || ip));
  const board = model.board;
  const requestPhase = phaseOf(NGINX_CARD_QUERIES.request, phases);
  const activePhase = phaseOf(NGINX_CARD_QUERIES.active, phases);
  const acceptPhase = phaseOf(NGINX_CARD_QUERIES.accept, phases);
  const collectionPhase = phaseOf(NGINX_CARD_QUERIES.collection, phases);
  const thirdPhase = board.focusThirdTab === 'connections' ? activePhase : phaseOf(NGINX_CARD_QUERIES.sitesKpi, phases);
  const failures = [collectionPhase, requestPhase, activePhase, alertPhase, requestPhase, acceptPhase, thirdPhase, requestPhase, acceptPhase]
    .filter((item) => item === 'error').length;
  const alertFigure = alertCount == null ? '暂无数据' : formatCount(Math.max(0, alertCount), '');
  const alertTone = alertCount != null && alertCount > 0 ? 'var(--color-fail)' : undefined;

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="overview">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="flex h-10 items-center rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-[13px]" data-nginx-host="">
        <LinkedHostSegment host={linked.host} href={linked.href} pending={linked.pending} />
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className="min-[1100px]:col-span-3">
          <NginxTile
            label="采集状态"
            hint={NGINX_HINTS.collection}
            figure={model.collection.label}
            sub={board.collectionSub}
            tone={model.collection.tone}
            phase={collectionPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.collection)}
          />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile
            label="请求速率"
            hint={NGINX_HINTS.request}
            unit="次/秒"
            figure={board.requestFigure}
            sub={board.requestSub}
            spark={model.requestPoints}
            phase={requestPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.request)}
          />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile
            label="活跃连接"
            hint={NGINX_HINTS.active}
            figure={board.activeFigure}
            sub={board.activeSub}
            spark={model.connSeries.find((item) => item.id === 'active')?.points}
            sparkStep
            phase={activePhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.active)}
          />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile
            label="告警数量"
            hint={NGINX_HINTS.alerts}
            figure={alertFigure}
            tone={alertTone}
            phase={alertPhase}
            emptyText={emptyText}
            onActivate={onOpenAlerts}
          />
        </div>
      </div>
      <section className="flex h-[72px] items-center overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3" data-nginx-events="">
        {alertPhase === 'error' ? (
          <div className="flex w-full items-center justify-center gap-3 text-[14px] text-[var(--color-text-3)]">
            加载失败
            <button type="button" className="text-[var(--color-primary)]" onClick={onRetryAlerts}>重试</button>
          </div>
        ) : (
          <EventsRail events={alertEvents} loading={alertPhase === 'loading'} onFocusAlert={onFocusAlert} />
        )}
      </section>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className="min-[1100px]:col-span-4">
          <NginxFocusTile
            label="请求是否骤变"
            hint={NGINX_HINTS.requestJump}
            unit="次/秒"
            figure={board.requestFigure}
            sub={board.focusRequestSub}
            phase={requestPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.request)}
            onOpen={() => onOpen('overview', 'nginx-request-trend')}
          />
        </div>
        <div className="min-[1100px]:col-span-4">
          <NginxFocusTile
            label="是否在丢连接"
            hint={[NGINX_HINTS.drops, NGINX_HINTS.handled]}
            unit="连接/秒"
            figure={board.droppedFigure}
            sub={board.handledFigure === '暂无数据' ? '' : `完成率 ${board.handledFigure}`}
            phase={acceptPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(NGINX_CARD_QUERIES.accept)}
            onOpen={() => onOpen('connections', 'nginx-dropped')}
          />
        </div>
        <div className="min-[1100px]:col-span-4">
          <NginxFocusTile
            label={board.focusThirdTitle}
            hint={board.focusThirdTab === 'connections'
              ? NGINX_HINTS.connStructure
              : [NGINX_HINTS.siteUpstream, NGINX_HINTS.upstreamDown]}
            figure={board.focusThirdFigure}
            sub={board.focusThirdSub}
            phase={thirdPhase}
            emptyText={emptyText}
            onRetry={() => onRetry(board.focusThirdTab === 'connections' ? NGINX_CARD_QUERIES.active : NGINX_CARD_QUERIES.sitesKpi)}
            onOpen={() => onOpen(board.focusThirdTab, board.focusThirdAnchor)}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <NginxChartCard
          anchor="nginx-request-trend"
          title="请求速率"
          hint={NGINX_HINTS.request}
          unit="次/秒"
          items={[{
            id: 'requests',
            label: '请求速率',
            color: '#27c274',
            points: model.requestPoints,
            reading: ''
          }]}
          floor={1}
          formatReading={rateText}
          phase={requestPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.request)}
        />
        <NginxChartCard
          title="连接接受与处理速率"
          hint={NGINX_HINTS.acceptHandled}
          unit="连接/秒"
          items={[
            { id: 'accepts', label: '接受速率', color: '#13c2c2', points: model.acceptPoints, reading: '' },
            { id: 'handled', label: '处理速率', color: '#597ef7', points: model.handledPoints, reading: '' }
          ]}
          floor={1}
          formatReading={connText}
          phase={acceptPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.accept)}
        />
      </div>
    </div>
  );
}
