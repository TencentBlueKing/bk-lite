'use client';

import { useEffect, useState, type ComponentType, type ReactNode } from 'react';
import { Button, Spin, Tabs, Tag } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import OperateDrawer from '@/components/operate-drawer';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';
import { useTranslation } from '@/utils/i18n';
import { buildAlarmHref, buildMonitorHrefFromContext, monitorObjectIdFromContext } from '../binding/links';
import { useArchitectureMonitorLink } from '../binding/useMonitorLink';
import type { ArchitectureNodeStatusItem } from '../binding/model';
import {
  buildRegionList,
  connectorEndpointNames,
  connectorResourceLines,
  diagramItemName,
  regionCaption,
  resourceTitle,
  STATUS_LABEL_KEY,
  type OverlayLabel,
  type RegionList,
  type ResourceLine,
} from '../binding/status';

export type ArchitectureDetailState =
  | {
    kind: 'resource';
    instUuid: string;
    modelId: string;
    highlightId?: string;
    returnTo?: ArchitectureDetailState;
  }
  | { kind: 'region'; rectangleId: string }
  | { kind: 'connector'; connectorId: string };

interface ResourceDetailDrawerProps {
  detail: ArchitectureDetailState;
  views: unknown;
  items: unknown;
  statusByUuid: Record<string, ArchitectureNodeStatusItem>;
  modelNames: Record<string, string>;
  onClose: () => void;
  onBack: () => void;
  onOpenResource: (target: { instUuid: string; modelId: string; highlightId?: string }) => void;
}

type DetailTab = 'cmdb' | 'monitor' | 'alerts';

const TAB_LABEL: Record<DetailTab, string> = {
  cmdb: 'dashboard.applicationTopologyCmdbTab',
  monitor: 'dashboard.applicationTopologyMonitorTab',
  alerts: 'dashboard.applicationTopologyAlertTab',
};

const labelText = (
  title: OverlayLabel,
  t: (key: string) => string,
) => {
  if (title.type === 'text') return title.value;
  if (title.type === 'invalid') return t('opsAnalysis.architecture.bindingInvalid');
  if (title.type === 'forbidden') return t('opsAnalysis.architecture.bindingForbidden');
  if (title.type === 'empty') return t('opsAnalysis.architecture.connectorEmpty');
  if (title.type === 'unknown') return t('opsAnalysis.architecture.bindingUnknown');
  return '';
};

const levelColor = (level: ArchitectureNodeStatusItem['status']) => {
  if (level === 'critical') return 'error';
  if (level === 'warning') return 'warning';
  if (level === 'normal') return 'success';
  return 'default';
};

const ResourceDetailDrawer = ({
  detail,
  views,
  items,
  statusByUuid,
  modelNames,
  onClose,
  onBack,
  onOpenResource,
}: ResourceDetailDrawerProps) => {
  const { t } = useTranslation();
  const showBack = detail.kind === 'resource' && Boolean(detail.returnTo);
  const resource = detail.kind === 'resource' ? detail : null;
  const regionList = detail.kind === 'region'
    ? buildRegionList(views, detail.rectangleId, statusByUuid, modelNames, items)
    : null;
  const lines = detail.kind === 'connector'
    ? connectorResourceLines(views, detail.connectorId, statusByUuid, modelNames, items)
    : [];
  const endpointNames = detail.kind === 'connector'
    ? connectorEndpointNames(views, items, detail.connectorId)
    : null;
  const status = resource ? statusByUuid[resource.instUuid] : undefined;
  const titleLabel = resource ? resourceTitle(status, modelNames) : null;
  const unnamed = t('opsAnalysis.architecture.unnamedIcon');
  const iconName = resource ? diagramItemName(items, resource.highlightId) : '';
  const missingResourceName = Boolean(
    titleLabel && titleLabel.type !== 'text' && titleLabel.type !== 'pending' && iconName,
  );
  const regionName = detail.kind === 'region' ? regionCaption(views, detail.rectangleId) : '';
  const heading = detail.kind === 'region'
    ? (regionName
      ? t('opsAnalysis.architecture.regionHeading', undefined, { name: regionName })
      : t('opsAnalysis.architecture.regionTitle'))
    : detail.kind === 'connector'
      ? t('opsAnalysis.architecture.connectorHeading', undefined, {
        start: endpointNames?.start || unnamed,
        end: endpointNames?.end || unnamed,
      })
      : missingResourceName
        ? iconName
        : titleLabel && titleLabel.type !== 'pending'
          ? labelText(titleLabel, t)
          : t('opsAnalysis.architecture.detailTitle');
  const headingTag = missingResourceName && titleLabel
    ? labelText(titleLabel, t)
    : '';

  return (
    <OperateDrawer
      open
      width={detail.kind === 'resource' ? 800 : 520}
      destroyOnHidden
      title={headingTag ? (
        <span className="inline-flex items-center gap-2">
          <span>{heading}</span>
          <Tag>{headingTag}</Tag>
        </span>
      ) : heading}
      onClose={onClose}
      classNames={{ body: 'flex min-h-0 flex-col overflow-hidden' }}
      styles={{ body: { overflow: 'hidden', padding: 0 } }}
      footer={(
        <Button onClick={onClose}>{t('dashboard.applicationTopologyCloseDetail')}</Button>
      )}
    >
        <div data-testid="architecture-detail" className="flex min-h-0 flex-1 flex-col">
          {showBack ? (
            <div className="px-4 pt-3">
              <Button type="link" className="px-0" onClick={onBack}>
                {t('opsAnalysis.architecture.backToList')}
              </Button>
            </div>
          ) : null}
          {detail.kind === 'resource' && resource ? (
            <ResourceBody
              instUuid={resource.instUuid}
              monitorId={status?.monitor_id || ''}
              blocked={titleLabel && (titleLabel.type === 'invalid' || titleLabel.type === 'forbidden')
                ? labelText(titleLabel, t)
                : ''}
            />
          ) : detail.kind === 'region' && regionList ? (
            <RegionListView list={regionList} onOpen={onOpenResource} />
          ) : (
            <ResourceLines
              testId="architecture-connector-detail"
              emptyLabel={t('opsAnalysis.architecture.connectorEmpty')}
              endpointLabel={[
                t('opsAnalysis.architecture.endpointStart'),
                t('opsAnalysis.architecture.endpointEnd'),
              ]}
              lines={lines}
              onOpen={onOpenResource}
            />
          )}
        </div>
    </OperateDrawer>
  );
};

const LineCard = ({
  line,
  prefix,
  onOpen,
}: {
  line: ResourceLine;
  prefix?: string;
  onOpen: ResourceDetailDrawerProps['onOpenResource'];
}) => {
  const { t } = useTranslation();
  const resourceName = line.title.type === 'text' ? labelText(line.title, t) : '';
  const iconFallback = !resourceName && line.iconName
    && line.title.type !== 'pending'
    && line.title.type !== 'empty'
    ? line.iconName
    : '';
  const title = resourceName || iconFallback || (line.title.type === 'pending' ? '' : labelText(line.title, t));
  const showStatusTag = Boolean(line.level) && (line.title.type === 'text' || Boolean(iconFallback));
  const statusLabel = showStatusTag && line.level
    ? (iconFallback ? labelText(line.title, t) : t(STATUS_LABEL_KEY[line.level]))
    : '';
  const meta = line.alertCount != null && line.title.type === 'text'
    ? t('opsAnalysis.architecture.alertCount', undefined, { count: line.alertCount })
    : '';
  const content = (
    <>
      {prefix ? (
        <div className="text-xs text-[var(--color-text-3)]">{prefix}</div>
      ) : null}
      <div className="flex items-center gap-2">
        {line.title.type === 'pending' ? <Spin size="small" /> : (
          <span className="text-sm text-[var(--color-text-1)]">{title}</span>
        )}
        {statusLabel && line.level ? (
          <Tag color={levelColor(line.level)}>{statusLabel}</Tag>
        ) : null}
      </div>
      {meta && line.title.type !== 'empty' ? (
        <div className="text-xs text-[var(--color-text-3)]">{meta}</div>
      ) : null}
    </>
  );
  if (!line.clickable) {
    return (
      <div
        data-testid={`architecture-resource-row-${line.key}`}
        className="rounded border border-[var(--color-border-2)] px-3 py-2"
      >
        {content}
      </div>
    );
  }
  return (
    <button
      type="button"
      data-testid={`architecture-resource-row-${line.key}`}
      className="rounded border border-[var(--color-border-2)] px-3 py-2 text-left hover:bg-[var(--color-fill-2)]"
      onClick={() => onOpen({
        instUuid: line.instUuid,
        modelId: line.modelId,
        highlightId: line.highlightId,
      })}
    >
      {content}
    </button>
  );
};

const ResourceLines = ({
  testId,
  emptyLabel,
  endpointLabel,
  lines,
  onOpen,
}: {
  testId: string;
  emptyLabel: string;
  endpointLabel?: string[];
  lines: ResourceLine[];
  onOpen: ResourceDetailDrawerProps['onOpenResource'];
}) => {
  if (!lines.length) {
    return (
      <div data-testid={testId} className="flex min-h-[280px] flex-1 items-center justify-center">
        <CompactEmptyState description={emptyLabel} />
      </div>
    );
  }
  return (
    <div data-testid={testId} className="flex flex-col gap-2 overflow-auto px-4 py-3">
      {lines.map((line, index) => (
        <LineCard
          key={line.key}
          line={line}
          prefix={endpointLabel?.[index]}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
};

const RegionListView = ({
  list,
  onOpen,
}: {
  list: RegionList;
  onOpen: ResourceDetailDrawerProps['onOpenResource'];
}) => {
  const { t } = useTranslation();
  return (
    <div data-testid="architecture-region-list" className="flex flex-col gap-3 overflow-auto px-4 py-3">
      <section className="flex flex-col gap-2">
        <div className="text-xs font-medium text-[var(--color-text-3)]">
          {t('opsAnalysis.architecture.regionIcons')}
        </div>
        {list.icons.length ? list.icons.map((line) => (
          <LineCard key={line.key} line={line} onOpen={onOpen} />
        )) : (
          <div className="text-sm text-[var(--color-text-3)]">
            {t('opsAnalysis.architecture.regionIconsEmpty')}
          </div>
        )}
      </section>
    </div>
  );
};

const ResourceBody = ({
  instUuid,
  monitorId,
  blocked,
}: {
  instUuid: string;
  monitorId: string;
  blocked: string;
}) => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<DetailTab>('cmdb');
  const [headerAction, setHeaderAction] = useState<ReactNode>(null);
  const linkContext = useArchitectureMonitorLink(monitorId);
  const baseInfo = useAppWidget('cmdb.baseInfo');
  const monitorView = useAppWidget('monitor.monitorView');
  const alertList = useAppWidget('monitor.alertList');
  const tabs: DetailTab[] = [];
  if (baseInfo.declared) tabs.push('cmdb');
  if (monitorView.declared) tabs.push('monitor');
  if (alertList.declared) tabs.push('alerts');
  const waiting = tabs.length === 0 && [baseInfo, monitorView, alertList].some(
    (widget) => widget.status === 'loading',
  );
  const activeTab = tabs.includes(tab) ? tab : tabs[0];
  const monitorReady = Boolean(monitorId);
  const baseWidget = useLazyAppWidget({
    loadWidget: baseInfo.loadWidget,
    active: activeTab === 'cmdb',
  });
  const monitorWidget = useLazyAppWidget({
    loadWidget: monitorReady ? monitorView.loadWidget : null,
    active: monitorReady && activeTab === 'monitor',
  });
  const alertWidget = useLazyAppWidget({
    loadWidget: monitorReady ? alertList.loadWidget : null,
    active: monitorReady && activeTab === 'alerts',
  });
  const BaseInfo = baseWidget.Widget as ComponentType<{
    instUuid: string;
    onHeaderAction?: (action: ReactNode) => void;
  }> | null;
  const MonitorView = monitorWidget.Widget as ComponentType<{
    monitorId: string;
  }> | null;
  const AlertList = alertWidget.Widget as ComponentType<{
    monitorId: string;
  }> | null;
  const monitorHref = activeTab === 'monitor' ? buildMonitorHrefFromContext(linkContext) : '';
  const alarmHref = activeTab === 'alerts' && linkContext && monitorId
    ? buildAlarmHref(monitorId, monitorObjectIdFromContext(linkContext))
    : '';
  const openHref = monitorHref || alarmHref;
  const openLabel = monitorHref
    ? t('opsAnalysis.architecture.linkOpenMonitor')
    : t('opsAnalysis.architecture.linkOpenAlarm');

  useEffect(() => {
    setHeaderAction(null);
    setTab('cmdb');
  }, [instUuid]);

  if (blocked) {
    return (
      <div className="flex min-h-[280px] flex-1 items-center justify-center">
        <CompactEmptyState description={blocked} />
      </div>
    );
  }

  return (
    <>
      {waiting ? (
        <div className="flex min-h-[280px] flex-1 items-center justify-center">
          <Spin />
        </div>
      ) : tabs.length === 0 ? (
        <div className="flex min-h-[280px] flex-1 items-center justify-center">
          <CompactEmptyState description={t('dashboard.applicationTopologyWidgetUnavailable')} />
        </div>
      ) : (
        <>
          <Tabs
            className="shrink-0 px-4 [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav]:before:shadow-none"
            activeKey={activeTab}
            items={tabs.map((key) => ({ key, label: t(TAB_LABEL[key]) }))}
            onChange={(value) => {
              setHeaderAction(null);
              setTab(value as DetailTab);
            }}
            tabBarExtraContent={activeTab === 'cmdb' ? headerAction : (
              openHref ? <Button type="link" href={openHref}>{openLabel}</Button> : null
            )}
          />
          <div className="min-h-0 flex-1 overflow-auto px-4 pt-3 pb-4">
            {activeTab === 'cmdb' ? (
              <WidgetSlot
                declared={baseInfo.declared}
                loading={
                  baseInfo.status === 'loading'
                  || (baseInfo.declared && !BaseInfo && !baseWidget.loadFailed)
                }
                failed={baseWidget.loadFailed}
              >
                {BaseInfo ? (
                  <BaseInfo instUuid={instUuid} onHeaderAction={setHeaderAction} />
                ) : null}
              </WidgetSlot>
            ) : null}
            {activeTab === 'monitor' || activeTab === 'alerts' ? (
              monitorReady ? (
                <WidgetSlot
                  declared={activeTab === 'monitor' ? monitorView.declared : alertList.declared}
                  loading={
                    (activeTab === 'monitor' ? monitorView.status : alertList.status) === 'loading'
                    || (activeTab === 'monitor'
                      ? monitorView.declared && !MonitorView && !monitorWidget.loadFailed
                      : alertList.declared && !AlertList && !alertWidget.loadFailed)
                  }
                  failed={activeTab === 'monitor' ? monitorWidget.loadFailed : alertWidget.loadFailed}
                >
                  {activeTab === 'monitor' && MonitorView ? (
                    <MonitorView monitorId={monitorId} />
                  ) : null}
                  {activeTab === 'alerts' && AlertList ? (
                    <AlertList monitorId={monitorId} />
                  ) : null}
                </WidgetSlot>
              ) : (
                <div className="flex h-40 items-center justify-center">
                  <CompactEmptyState description={t('dashboard.applicationTopologyUnmonitored')} />
                </div>
              )
            ) : null}
          </div>
        </>
      )}
    </>
  );
};

const WidgetSlot = ({
  declared,
  loading,
  failed,
  children,
}: {
  declared: boolean;
  loading: boolean;
  failed: boolean;
  children: ReactNode;
}) => {
  const { t } = useTranslation();
  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (!declared || failed) {
    return (
      <div className="flex h-40 items-center justify-center">
        <CompactEmptyState description={t('dashboard.applicationTopologyWidgetUnavailable')} />
      </div>
    );
  }
  return <>{children}</>;
};

export default ResourceDetailDrawer;
