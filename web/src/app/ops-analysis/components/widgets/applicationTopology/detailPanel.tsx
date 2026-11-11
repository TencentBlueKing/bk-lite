'use client';

import React, { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Button, ConfigProvider, Spin, Tabs } from 'antd';
import type { ThemeConfig } from 'antd/es/config-provider/context';
import CompactEmptyState from '@/components/compact-empty-state';
import OperateDrawer from '@/components/operate-drawer';
import {
  APP_VIEW_FULLSCREEN_EVENT,
  isAppViewFullscreenActive,
} from '@/components/app-view-fullscreen';
import {
  buildScreenContentTokenStyle,
  createScreenAntdTheme,
} from '@/app/ops-analysis/utils/screenWidgetTokens';
import {
  isScreenChartThemeMode,
  type OpsChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';
import { createAntdTheme } from '@/theme/antd-adapter';
import {
  useOptionalThemeMode,
  useOptionalThemeTokens,
  type SemanticColorTokens,
  type ThemeMode,
} from '@/theme';
import { useTranslation } from '@/utils/i18n';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';
import type { ApplicationTopologyBandNode } from './bandModel';
import styles from './detailPanel.module.scss';

/** 大屏单独呈现时抽屉会离开画布，用实色，避免半透明表面透出底下的画面。 */
const SCREEN_DRAWER_SURFACE = {
  'screen-dark': '#14243a',
  'screen-light': '#ffffff',
} as const;

const SYSTEM_DRAWER_SURFACE = 'var(--color-modal-header-color)';

const applicationTopologyDrawerSurface = (mode?: OpsChartThemeMode) => (
  mode === 'screen-dark' || mode === 'screen-light'
    ? SCREEN_DRAWER_SURFACE[mode]
    : SYSTEM_DRAWER_SURFACE
);

/**
 * 页面上只剩大屏、没有系统外壳时，详情才跟随大屏主题。
 * 分享页用已有 shareMode；全屏预览用 data-app-view-fullscreen；
 * 浏览器全屏（轮播播放）与 fullscreenPopupContainer 同一条件。
 */
export function screenDetailFollowsScreenTheme(input: {
  shareMode: boolean;
  appViewFullscreen: boolean;
  browserFullscreen: boolean;
}): boolean {
  return input.shareMode || input.appViewFullscreen || input.browserFullscreen;
}

export function readScreenDetailPresentation(shareMode: boolean): boolean {
  if (shareMode) return true;
  if (typeof document === 'undefined') return false;
  return screenDetailFollowsScreenTheme({
    shareMode: false,
    appViewFullscreen: isAppViewFullscreenActive(),
    browserFullscreen: document.fullscreenElement instanceof HTMLElement,
  });
}

export function resolveApplicationTopologyDetailChrome(input: {
  chartThemeMode?: OpsChartThemeMode;
  presentedAlone: boolean;
  systemMode: ThemeMode;
  systemTokens: SemanticColorTokens;
}): {
  theme?: ThemeConfig;
  /** 只有大屏单独呈现时才铺实色。内嵌预览留空，交给 OperateDrawer 默认表面。 */
  surface?: string;
  contentStyle?: CSSProperties;
} {
  const followScreen = isScreenChartThemeMode(input.chartThemeMode) && input.presentedAlone;
  if (followScreen) {
    const theme = createScreenAntdTheme(input.chartThemeMode, input.systemTokens);
    return {
      theme: theme ? { ...theme, inherit: false } : undefined,
      surface: applicationTopologyDrawerSurface(input.chartThemeMode),
      contentStyle: buildScreenContentTokenStyle(input.chartThemeMode),
    };
  }
  // 大屏组件外层 ConfigProvider 会穿过门户。内嵌预览用系统主题盖住它，
  // 表面色不再改写，标题/正文/底栏走 OperateDrawer 默认样式。
  if (isScreenChartThemeMode(input.chartThemeMode)) {
    return {
      theme: {
        ...createAntdTheme(input.systemMode, input.systemTokens),
        inherit: false,
      },
      surface: undefined,
      contentStyle: undefined,
    };
  }
  return {
    theme: undefined,
    surface: undefined,
    contentStyle: undefined,
  };
}

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
  const systemMode = useOptionalThemeMode();
  const [presentedAlone, setPresentedAlone] = useState(() => (
    readScreenDetailPresentation(shareMode)
  ));
  useEffect(() => {
    const sync = () => setPresentedAlone(readScreenDetailPresentation(shareMode));
    sync();
    window.addEventListener(APP_VIEW_FULLSCREEN_EVENT, sync);
    document.addEventListener('fullscreenchange', sync);
    return () => {
      window.removeEventListener(APP_VIEW_FULLSCREEN_EVENT, sync);
      document.removeEventListener('fullscreenchange', sync);
    };
  }, [shareMode]);
  const chrome = useMemo(
    () => resolveApplicationTopologyDetailChrome({
      chartThemeMode,
      presentedAlone,
      systemMode,
      systemTokens,
    }),
    [chartThemeMode, presentedAlone, systemMode, systemTokens],
  );
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

  const screenSurface = chrome.surface
    ? {
      '--ops-topology-drawer-surface': chrome.surface,
      ...chrome.contentStyle,
    } as React.CSSProperties
    : undefined;
  const drawer = (
    <OperateDrawer
      open
      width={800}
      getContainer={fullscreenPopupContainer}
      title={node.name}
      subTitle={`${node.modelId} · ${statusLabel}`}
      destroyOnHidden
      onClose={onClose}
      rootClassName={screenSurface ? styles.shell : undefined}
      style={screenSurface}
      classNames={{ body: 'flex min-h-0 flex-col overflow-hidden' }}
      styles={{
        header: screenSurface ? { boxShadow: 'none' } : undefined,
        body: {
          overflow: 'hidden',
          padding: 0,
          ...(screenSurface ? { background: 'transparent' } : {}),
        },
      }}
      footer={(
        <div>
          <Button onClick={onClose}>{t('dashboard.applicationTopologyCloseDetail')}</Button>
        </div>
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden" style={chrome.contentStyle}>
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

  if (!chrome.theme) return drawer;
  return <ConfigProvider theme={chrome.theme}>{drawer}</ConfigProvider>;
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
