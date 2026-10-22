'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, ConfigProvider, Spin, Tabs } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import OperateDrawer from '@/components/operate-drawer';
import {
  buildScreenContentTokenStyle,
  createScreenAntdTheme,
} from '@/app/ops-analysis/utils/screenWidgetTokens';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';
import { useOptionalThemeTokens } from '@/theme';
import { useTranslation } from '@/utils/i18n';
import type { ApplicationTopologyBandNode } from './bandModel';
import styles from './detailPanel.module.scss';

/** 大屏抽屉门户到 body，用实色，避免半透明表面透出系统页。 */
const SCREEN_DRAWER_SURFACE = {
  'screen-dark': '#14243a',
  'screen-light': '#ffffff',
} as const;

const applicationTopologyDrawerSurface = (mode?: OpsChartThemeMode) => (
  mode === 'screen-dark' || mode === 'screen-light'
    ? SCREEN_DRAWER_SURFACE[mode]
    : 'var(--color-modal-header-color)'
);

export type ApplicationTopologyDetailTabKey = 'cmdb' | 'monitor' | 'alerts';

export function resolveApplicationTopologyDetailTabs(input: {
  shareMode: boolean;
  baseInfoDeclared: boolean;
  monitorViewDeclared: boolean;
  alertListDeclared: boolean;
}): ApplicationTopologyDetailTabKey[] {
  if (input.shareMode) return [];
  const tabs: ApplicationTopologyDetailTabKey[] = [];
  if (input.baseInfoDeclared) tabs.push('cmdb');
  if (input.monitorViewDeclared) tabs.push('monitor');
  if (input.alertListDeclared) tabs.push('alerts');
  return tabs;
}

interface ApplicationTopologyDetailPanelProps {
  node: ApplicationTopologyBandNode;
  statusLabel: string;
  shareMode: boolean;
  chartThemeMode?: OpsChartThemeMode;
  onClose: () => void;
}

const TAB_LABEL_KEY: Record<ApplicationTopologyDetailTabKey, string> = {
  cmdb: 'dashboard.applicationTopologyCmdbTab',
  monitor: 'dashboard.applicationTopologyMonitorTab',
  alerts: 'dashboard.applicationTopologyAlertTab',
};

const ApplicationTopologyDetailPanel = ({
  node,
  statusLabel,
  shareMode,
  chartThemeMode,
  onClose,
}: ApplicationTopologyDetailPanelProps) => {
  const { t } = useTranslation();
  const systemTokens = useOptionalThemeTokens();
  const screenTheme = useMemo(() => {
    const theme = createScreenAntdTheme(chartThemeMode, systemTokens);
    if (!theme) return undefined;
    return { ...theme, inherit: false as const };
  }, [chartThemeMode, systemTokens]);
  const contentTokenStyle = buildScreenContentTokenStyle(chartThemeMode);
  const drawerSurface = applicationTopologyDrawerSurface(chartThemeMode);
  const [tab, setTab] = useState<ApplicationTopologyDetailTabKey>('cmdb');
  const [headerAction, setHeaderAction] = useState<React.ReactNode>(null);
  const baseInfo = useAppWidget('cmdb.baseInfo');
  const monitorView = useAppWidget('monitor.monitorView');
  const alertList = useAppWidget('monitor.alertList');
  const tabs = resolveApplicationTopologyDetailTabs({
    shareMode,
    baseInfoDeclared: baseInfo.declared,
    monitorViewDeclared: monitorView.declared,
    alertListDeclared: alertList.declared,
  });
  const waiting = tabs.length === 0 && [baseInfo, monitorView, alertList].some(
    (widget) => widget.status === 'loading',
  );
  const activeTab = tabs.includes(tab) ? tab : tabs[0];
  const monitorReady = Boolean(node.monitorId) && !shareMode;
  const baseWidget = useLazyAppWidget({
    loadWidget: shareMode ? null : baseInfo.loadWidget,
    active: !shareMode && activeTab === 'cmdb',
  });
  const monitorWidget = useLazyAppWidget({
    loadWidget: monitorReady ? monitorView.loadWidget : null,
    active: monitorReady && activeTab === 'monitor',
  });
  const alertWidget = useLazyAppWidget({
    loadWidget: monitorReady ? alertList.loadWidget : null,
    active: monitorReady && activeTab === 'alerts',
  });

  useEffect(() => {
    setHeaderAction(null);
    setTab('cmdb');
  }, [node.id]);

  const BaseInfo = baseWidget.Widget as React.ComponentType<{
    instUuid: string;
    onHeaderAction?: (action: React.ReactNode) => void;
  }> | null;
  const MonitorView = monitorWidget.Widget as React.ComponentType<{ monitorId: string }> | null;
  const AlertList = alertWidget.Widget as React.ComponentType<{ monitorId: string }> | null;

  const drawer = (
    <OperateDrawer
      open
      width={800}
      getContainer={() => document.body}
      title={node.name}
      subTitle={`${node.modelId} · ${statusLabel}`}
      destroyOnHidden
      onClose={onClose}
      rootClassName={styles.shell}
      style={{ '--ops-topology-drawer-surface': drawerSurface } as React.CSSProperties}
      classNames={{ body: 'flex min-h-0 flex-col overflow-hidden' }}
      styles={{
        header: { boxShadow: 'none' },
        body: { overflow: 'hidden', padding: 0, background: 'transparent' },
      }}
      footer={(
        <div>
          <Button onClick={onClose}>{t('dashboard.applicationTopologyCloseDetail')}</Button>
        </div>
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden" style={contentTokenStyle}>
      {shareMode ? (
        <div className="flex min-h-[280px] flex-1 items-center justify-center">
          <CompactEmptyState description={t('dashboard.applicationTopologyShareDetail')} />
        </div>
      ) : waiting ? (
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
            items={tabs.map((key) => ({ key, label: t(TAB_LABEL_KEY[key]) }))}
            onChange={(value) => {
              setHeaderAction(null);
              setTab(value as ApplicationTopologyDetailTabKey);
            }}
            tabBarExtraContent={activeTab === 'cmdb' ? headerAction : null}
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
                unavailableText={t('dashboard.applicationTopologyWidgetUnavailable')}
              >
                {BaseInfo ? (
                  <BaseInfo instUuid={node.id} onHeaderAction={setHeaderAction} />
                ) : null}
              </WidgetSlot>
            ) : null}
            {activeTab === 'monitor' || activeTab === 'alerts' ? (
              node.monitorId ? (
                <WidgetSlot
                  declared={activeTab === 'monitor' ? monitorView.declared : alertList.declared}
                  loading={
                    (activeTab === 'monitor' ? monitorView.status : alertList.status) === 'loading'
                    || (activeTab === 'monitor'
                      ? monitorView.declared && !MonitorView && !monitorWidget.loadFailed
                      : alertList.declared && !AlertList && !alertWidget.loadFailed)
                  }
                  failed={activeTab === 'monitor' ? monitorWidget.loadFailed : alertWidget.loadFailed}
                  unavailableText={t('dashboard.applicationTopologyWidgetUnavailable')}
                >
                  {activeTab === 'monitor' && MonitorView ? (
                    <MonitorView monitorId={node.monitorId} />
                  ) : null}
                  {activeTab === 'alerts' && AlertList ? (
                    <AlertList monitorId={node.monitorId} />
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
      </div>
    </OperateDrawer>
  );

  if (!screenTheme) return drawer;
  return <ConfigProvider theme={screenTheme}>{drawer}</ConfigProvider>;
};

const WidgetSlot = ({
  declared,
  loading,
  failed,
  unavailableText,
  children,
}: {
  declared: boolean;
  loading: boolean;
  failed: boolean;
  unavailableText: string;
  children: React.ReactNode;
}) => {
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
        <CompactEmptyState description={unavailableText} />
      </div>
    );
  }
  return <>{children}</>;
};

export default ApplicationTopologyDetailPanel;
