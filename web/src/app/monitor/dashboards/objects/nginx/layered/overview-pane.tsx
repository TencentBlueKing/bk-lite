'use client';

import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { ProSection } from '../../host/layered/section-title';
import { formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxFocusTile, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxHint } from './nginx-hint';
import type { NginxDashboardModel } from './model';
import { NGINX_CARD_QUERIES, focusCardQueries, phaseOf, type NginxQueryPhase } from './query-phase';

export type NginxTabKey = 'overview' | 'connections' | 'sites' | 'upstream';

const rateText = (value: number) => formatPerSecond(value, '次');
const connText = (value: number) => formatPerSecond(value, '连接');
const CELL = 'flex min-w-0 min-[1100px]:col-span-3';
const THIRD = 'flex min-w-0 min-[1100px]:col-span-4';

export default function OverviewPane({
  model,
  phases,
  alertPhase,
  emptyText,
  alertEvents,
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
  const board = model.board;
  const requestPhase = phaseOf(NGINX_CARD_QUERIES.request, phases);
  const activePhase = phaseOf(NGINX_CARD_QUERIES.active, phases);
  const acceptPhase = phaseOf(NGINX_CARD_QUERIES.accept, phases);
  const droppedPhase = phaseOf(NGINX_CARD_QUERIES.droppedCount, phases);
  const thirdKeys = focusCardQueries(board.focusThirdTab);
  const thirdPhase = phaseOf(thirdKeys, phases);
  const thirdHint = board.focusThirdTab === 'connections' ? NGINX_HINTS.connStructure : NGINX_HINTS.siteUpstream;
  const thirdUnit = board.focusThirdTab === 'connections' ? '个' : '次';
  const failures = [
    requestPhase,
    activePhase,
    activePhase,
    droppedPhase,
    alertPhase,
    requestPhase,
    acceptPhase,
    thirdPhase,
    requestPhase,
    acceptPhase
  ].filter((item) => item === 'error').length;

  return (
    <div className="flex flex-col gap-6" data-nginx-pane="overview">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <ProSection id="nginx-health" title="健康概览">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
          <div className={CELL} data-nginx-width="1/4">
            <NginxTile
              label="请求速率"
              hint={NGINX_HINTS.request}
              unit="次/秒"
              figure={board.requestFigure}
              sub={board.requestSub}
              phase={requestPhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.request)}
            />
          </div>
          <div className={CELL} data-nginx-width="1/4">
            <NginxTile
              label="活跃连接"
              hint={NGINX_HINTS.active}
              unit="个"
              figure={board.activeFigure}
              sub={board.activeSub}
              phase={activePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.active)}
            />
          </div>
          <div className={CELL} data-nginx-width="1/4">
            <NginxTile
              label="等待连接"
              hint={NGINX_HINTS.waiting}
              unit="个"
              figure={board.waitingFigure}
              phase={activePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.active)}
            />
          </div>
          <div className={CELL} data-nginx-width="1/4">
            <NginxTile
              label="丢弃连接"
              hint={NGINX_HINTS.droppedCount}
              unit="次"
              figure={board.droppedCountFigure}
              tone={board.droppedCountHot ? 'var(--color-fail)' : undefined}
              phase={droppedPhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.droppedCount)}
            />
          </div>
        </div>
      </ProSection>
      <ProSection id="nginx-events" title="事件" hint={<NginxHint copy={NGINX_HINTS.events} />}>
        <div className="h-[72px]" data-nginx-events="">
          {alertPhase === 'error' ? (
            <div className="flex h-[72px] items-center justify-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-[14px] text-[var(--color-text-3)]">
              加载失败
              <button type="button" className="text-[var(--color-primary)]" onClick={onRetryAlerts}>重试</button>
            </div>
          ) : (
            <EventsRail
              className="box-border !h-[72px] !min-h-[72px] w-full"
              events={alertEvents}
              loading={alertPhase === 'loading'}
              onFocusAlert={onFocusAlert}
            />
          )}
        </div>
      </ProSection>
      <ProSection id="nginx-focus" title="重点关注">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
          <div className={THIRD} data-nginx-width="1/3">
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
          <div className={THIRD} data-nginx-width="1/3">
            <NginxFocusTile
              label="是否在丢连接"
              hint={NGINX_HINTS.connectionLoss}
              unit="连接/秒"
              figure={board.droppedFigure}
              sub={board.handledFigure === '暂无数据' ? '' : `完成率 ${board.handledFigure}`}
              phase={acceptPhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.accept)}
              onOpen={() => onOpen('connections', 'nginx-dropped')}
            />
          </div>
          <div className={THIRD} data-nginx-width="1/3">
            <NginxFocusTile
              label={board.focusThirdTitle}
              hint={thirdHint}
              unit={board.focusThirdFigure === '暂无数据' ? undefined : thirdUnit}
              figure={board.focusThirdFigure}
              sub={board.focusThirdSub}
              phase={thirdPhase}
              emptyText={emptyText}
              onRetry={() => onRetry(thirdKeys)}
              onOpen={() => onOpen(board.focusThirdTab, board.focusThirdAnchor)}
            />
          </div>
        </div>
      </ProSection>
      <ProSection id="nginx-trends" title="趋势">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
          <div data-nginx-width="1/2">
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
          </div>
          <div data-nginx-width="1/2">
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
      </ProSection>
    </div>
  );
}
