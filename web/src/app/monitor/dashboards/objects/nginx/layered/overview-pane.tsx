'use client';

import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { ProSection } from '../../host/layered/section-title';
import { formatCount, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NGINX_SPAN, NginxChartCard, NginxFocusTile, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxHint } from './nginx-hint';
import type { NginxDashboardModel, NginxSeriesItem, Point } from './model';
import { NGINX_CARD_QUERIES, focusCardQueries, phaseOf, type NginxQueryPhase } from './query-phase';

export type NginxTabKey = 'overview' | 'connections' | 'sites' | 'upstream';

const rateText = (value: number) => formatPerSecond(value, '次');
const connText = (value: number) => formatPerSecond(value, '连接');
const countText = (value: number) => formatCount(value, '次');

const lineOf = (
  id: string,
  label: string,
  color: string,
  points: readonly Point[]
): NginxSeriesItem => ({ id, label, color, points: [...points], reading: '' });

const sumPoints = (left: readonly Point[], right: readonly Point[]) => {
  const bucket = new Map<number, number>();
  left.forEach((point) => bucket.set(point.time, (bucket.get(point.time) ?? 0) + point.value));
  right.forEach((point) => bucket.set(point.time, (bucket.get(point.time) ?? 0) + point.value));
  return Array.from(bucket.entries()).map(([time, value]) => ({ time, value })).sort((a, b) => a.time - b.time);
};

export default function OverviewPane({
  model,
  phases,
  alertPhase,
  emptyText,
  alertCount,
  alertEvents,
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
  const board = model.board;
  const requestPhase = phaseOf(NGINX_CARD_QUERIES.request, phases);
  const activePhase = phaseOf(NGINX_CARD_QUERIES.active, phases);
  const acceptPhase = phaseOf(NGINX_CARD_QUERIES.accept, phases);
  const droppedPhase = phaseOf(NGINX_CARD_QUERIES.droppedCount, phases);
  const thirdKeys = focusCardQueries(board.focusThirdTab);
  const thirdPhase = phaseOf(thirdKeys, phases);
  const thirdHint = board.focusThirdTab === 'connections' ? NGINX_HINTS.connStructure : NGINX_HINTS.siteUpstream;
  const thirdUnit = board.focusThirdTab === 'connections' ? '个' : '次';
  const requestSeries = model.requestPoints.length
    ? [lineOf('requests', '请求速率', '#27c274', model.requestPoints)]
    : [];
  const dropSeries = model.droppedPoints.length
    ? [lineOf('dropped', '丢弃连接速率', '#ff7875', model.droppedPoints)]
    : [];
  const readingPoints = model.connSeries.find((item) => item.id === 'reading')?.points ?? [];
  const writingPoints = model.connSeries.find((item) => item.id === 'writing')?.points ?? [];
  const waitingPoints = model.connSeries.find((item) => item.id === 'waiting')?.points ?? [];
  const busyPoints = sumPoints(readingPoints, writingPoints);
  const structureSeries = [
    ...(busyPoints.length ? [lineOf('busy', '读写', '#ff8a1f', busyPoints)] : []),
    ...(waitingPoints.length ? [lineOf('waiting', '等待', '#8a5cff', waitingPoints)] : [])
  ];
  const fiveSeries = board.statusSteps.find((item) => item.id === '5xx');
  const fiveScaffold = board.statusSteps.find((item) => item.points.length)?.points ?? model.requestPoints;
  const anomalySeries = board.focusThirdFigure === '暂无数据'
    ? []
    : fiveSeries?.points.length
      ? [lineOf('5xx', '5xx', '#ff4d4f', fiveSeries.points)]
      : fiveScaffold.length
        ? [lineOf('5xx', '5xx', '#ff4d4f', fiveScaffold.map((point) => ({ time: point.time, value: 0 })))]
        : [];
  const thirdSeries = board.focusThirdTab === 'connections' ? structureSeries : anomalySeries;
  const thirdFormat = board.focusThirdTab === 'connections'
    ? (value: number) => formatCount(value, '个')
    : countText;
  const requestFocusSub = board.requestFigure === '暂无数据' ? board.requestSub : board.focusRequestSub;
  const dropFocusSub = board.droppedFigure === '暂无数据'
    ? board.droppedCountSub
    : board.handledFigure === '暂无数据' ? '完成率 暂无数据' : `完成率 ${board.handledFigure}`;
  const thirdSub = board.focusThirdFigure === '暂无数据' && !board.focusThirdSub
    ? board.activeSub
    : board.focusThirdSub;
  const alertFigure = alertCount == null ? '--' : String(alertCount);
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
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
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
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
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
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
            <NginxTile
              label="告警数量"
              hint={NGINX_HINTS.alerts}
              figure={alertFigure}
              tone={alertCount != null && alertCount > 0 ? 'var(--color-fail)' : undefined}
              phase={alertPhase}
              emptyText={emptyText}
              onRetry={onRetryAlerts}
              onActivate={onOpenAlerts}
            />
          </div>
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxTile
              label="等待连接"
              hint={NGINX_HINTS.waiting}
              unit="个"
              figure={board.waitingFigure}
              sub={board.waitingSub}
              phase={activePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.active)}
            />
          </div>
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxTile
              label="丢弃连接"
              hint={NGINX_HINTS.droppedCount}
              unit="次"
              figure={board.droppedCountFigure}
              sub={board.droppedCountSub}
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
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
            <NginxFocusTile
              label="请求是否骤变"
              hint={NGINX_HINTS.requestJump}
              unit="次/秒"
              figure={board.requestFigure}
              sub={requestFocusSub}
              series={requestSeries}
              formatReading={rateText}
              phase={requestPhase}
              emptyText={emptyText}
              emptyDetail={board.requestSub}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.request)}
              onOpen={() => onOpen('overview', 'nginx-request-trend')}
            />
          </div>
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
            <NginxFocusTile
              label="是否在丢连接"
              hint={NGINX_HINTS.connectionLoss}
              unit="连接/秒"
              figure={board.droppedFigure}
              sub={dropFocusSub}
              series={dropSeries}
              formatReading={connText}
              tone={board.droppedFigure !== '暂无数据' && Number(board.droppedFigure) > 0 ? 'var(--color-fail)' : undefined}
              phase={acceptPhase}
              emptyText={emptyText}
              emptyDetail={board.droppedCountSub}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.accept)}
              onOpen={() => onOpen('connections', 'nginx-dropped')}
            />
          </div>
          <div className={NGINX_SPAN.third} data-nginx-width="1/3">
            <NginxFocusTile
              label={board.focusThirdTitle}
              hint={thirdHint}
              unit={thirdUnit}
              figure={board.focusThirdFigure}
              sub={thirdSub}
              series={thirdSeries}
              formatReading={thirdFormat}
              countAxis
              tone={board.focusThirdTab !== 'connections' && board.focusThirdFigure !== '暂无数据' && Number(board.focusThirdFigure) > 0 ? 'var(--color-fail)' : undefined}
              phase={thirdPhase}
              emptyText={emptyText}
              emptyDetail={board.focusThirdTab === 'connections' ? board.activeSub : board.focusThirdSub}
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
