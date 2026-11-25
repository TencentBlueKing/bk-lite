'use client';

import { ProFocusCard, ProSection } from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import host from '../../host/layered/layered.module.scss';
import { formatDuration, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxDimensionalChart } from './dimensional-chart';
import { NginxKpiRow } from './kpi-row';
import type { NginxDashboardModel } from './model';
import { NginxHint } from './nginx-hint';

export type NginxTabKey = 'overview' | 'connections' | 'sites' | 'upstream';

const rateReading = (value: number) => formatPerSecond(value, '次');

export default function OverviewPane({
  model,
  loading,
  emptyText,
  alertCount,
  alertsOpen,
  alertEvents,
  eventsLoading,
  onOpenAlerts,
  onFocusAlert,
  onOpen
}: {
  model: NginxDashboardModel;
  loading: boolean;
  emptyText: string;
  alertCount: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpen: (tab: NginxTabKey) => void;
}) {
  const alertValue = alertCount == null || !Number.isFinite(alertCount) ? '暂无数据' : String(Math.max(0, Math.round(alertCount)));
  const alertTone = alertCount == null ? undefined : alertCount > 0 ? 'var(--color-fail)' : 'var(--color-success)';
  const requestSeries = [{
    id: 'requests',
    label: '请求速率',
    color: '#27c274',
    points: model.requestPoints,
    reading: model.request
  }];
  const acceptSeries = [
    { id: 'accepts', label: '接受速率', color: '#13c2c2', points: model.acceptPoints, reading: model.accepts },
    { id: 'handled', label: '处理速率', color: '#597ef7', points: model.handledPoints, reading: model.handledRate }
  ];
  const timeSeries = model.showRequestTime ? [{
    id: 'star',
    label: '汇总',
    color: '#2f6bff',
    points: model.requestTimePoints,
    reading: model.requestTime
  }] : [];
  const focus = [
    {
      key: 'request',
      title: '请求是否骤变',
      hint: NGINX_HINTS.request,
      value: model.focus.requestValue,
      detail: model.focus.requestDetail,
      tab: model.focus.requestTab,
      cta: '查看请求与站点'
    },
    {
      key: 'connections',
      title: '连接结构',
      hint: NGINX_HINTS.busy,
      value: model.focus.connectionValue,
      detail: model.focus.connectionDetail,
      tab: 'connections' as const,
      cta: '查看连接'
    },
    {
      key: 'drops',
      title: '是否在丢连接',
      hint: NGINX_HINTS.dropped,
      value: model.focus.dropValue,
      detail: model.focus.dropDetail,
      tab: 'connections' as const,
      cta: '查看连接'
    },
    {
      key: 'fourth',
      title: model.focus.fourthTitle,
      hint: model.focus.fourthTab === 'upstream' ? NGINX_HINTS.upstreamDown : model.focus.fourthTab === 'sites' ? NGINX_HINTS.codes : NGINX_HINTS.waiting,
      value: model.focus.fourthValue,
      detail: model.focus.fourthDetail,
      tab: model.focus.fourthTab,
      cta: model.focus.fourthTab === 'sites' ? '查看请求与站点' : model.focus.fourthTab === 'upstream' ? '查看上游' : '查看连接'
    }
  ];

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="overview">
      <ProSection title="健康概览">
        <NginxKpiRow
          loading={loading}
          items={[
            { key: 'collection', label: '采集状态', value: model.collection.label, tone: model.collection.tone, hint: NGINX_HINTS.collection },
            { key: 'request', label: '请求速率', value: model.request, hint: NGINX_HINTS.request },
            { key: 'active', label: '活跃连接', value: model.active, hint: NGINX_HINTS.active },
            { key: 'dropped', label: '丢弃连接速率', value: model.dropped, hint: NGINX_HINTS.dropped },
            { key: 'handled', label: '连接处理完成率', value: model.handled, hint: NGINX_HINTS.handled },
            {
              key: 'alerts',
              label: '告警数量',
              value: alertValue,
              tone: alertTone,
              hint: NGINX_HINTS.alerts,
              onActivate: onOpenAlerts,
              expanded: alertsOpen
            }
          ]}
        />
      </ProSection>
      <ProSection title="事件" hint={<NginxHint copy={NGINX_HINTS.events} />}>
        <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />
      </ProSection>
      <ProSection title="重点关注">
        <div className={host.shortcutGrid}>
          {focus.map((card) => {
            const body = (
              <ProFocusCard>
                <div className={host.shortcutCopy}>
                  <div className={`${host.kpiLabel} inline-flex items-center gap-1`}>
                    {card.title}
                    <NginxHint copy={card.hint} />
                  </div>
                  <div className={host.shortcutMain}>{loading ? ' ' : card.value}</div>
                  <div className={host.shortcutSub}>{card.detail}</div>
                  {card.tab ? <span className={host.jumpBtn}>{card.cta}</span> : null}
                </div>
              </ProFocusCard>
            );
            if (!card.tab) return <div key={card.key}>{body}</div>;
            return (
              <button
                key={card.key}
                type="button"
                className="border-0 bg-transparent p-0 text-left"
                onClick={() => onOpen(card.tab as NginxTabKey)}
              >
                {body}
              </button>
            );
          })}
        </div>
      </ProSection>
      <ProSection title="趋势">
        <div className="grid grid-cols-1 gap-3 min-[1100px]:grid-cols-2">
          <NginxDimensionalChart
            title="请求速率"
            hint={NGINX_HINTS.request}
            items={requestSeries}
            floor={1}
            formatReading={rateReading}
            loading={loading}
            emptyText={emptyText}
          />
          <NginxDimensionalChart
            title="连接接受与处理"
            hint={NGINX_HINTS.acceptHandled}
            items={acceptSeries}
            floor={1}
            formatReading={(value) => formatPerSecond(value, '连接')}
            loading={loading}
            emptyText={emptyText}
          />
          {model.showRequestTime ? (
            <NginxDimensionalChart
              title="平均处理时间"
              hint={NGINX_HINTS.zoneTime}
              items={timeSeries}
              floor={10}
              formatReading={(value) => formatDuration(value, model.requestTimeUnit)}
              loading={loading}
              emptyText={emptyText}
            />
          ) : null}
        </div>
      </ProSection>
    </div>
  );
}
