'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Select, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { useClientData } from '@/context/client';
import {
  hasAppAccess,
  useAppWidget,
  useLazyAppWidget,
} from '@/context/appCapabilities';
import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';
import {
  alarmHasAnyInstUuid,
  alarmHasAnyMonitorId,
  listAlarmSnapshotObjects,
  type AlarmSnapshotObject,
} from '@/app/alarm/utils/alarmSnapshotObjects';
import { buildAlarmDetailPublicTabs } from '@/app/alarm/utils/alarmDetailPublicTabs';
import { resolveAlarmPublicWidgetVisibility } from '@/app/alarm/utils/alarmPublicWidgetVisibility';

type InstUuidWidget = React.ComponentType<{
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
}>;
type MonitorIdWidget = React.ComponentType<{ monitorId: string; metricKey?: string }>;

export function useAlarmPublicWidgets(options: {
  monitorObjects?: MonitorObjectSnapshot[];
  includeActionRecords: boolean;
  activeTab: string;
}) {
  const { clientData } = useClientData();
  const hasOpsAnalysis = hasAppAccess(clientData, 'ops-analysis');
  const monitorView = useAppWidget('monitor.monitorView');
  const relatedTopology = useAppWidget('ops-analysis.relatedTopology');
  const assetInfo = useAppWidget('cmdb.baseInfo');
  const objects = useMemo(
    () => listAlarmSnapshotObjects(options.monitorObjects),
    [options.monitorObjects],
  );
  const {
    monitorView: showMonitorView,
    relatedTopology: showRelatedTopology,
    assetInfo: showAssetInfo,
  } = resolveAlarmPublicWidgetVisibility({
    hasOpsAnalysis,
    monitorViewDeclared: monitorView.declared,
    relatedTopologyDeclared: relatedTopology.declared,
    assetInfoDeclared: assetInfo.declared,
    hasMonitorId: alarmHasAnyMonitorId(options.monitorObjects),
    hasInstUuid: alarmHasAnyInstUuid(options.monitorObjects),
  });

  const { t } = useTranslation();
  const tabs = useMemo(
    () =>
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: options.includeActionRecords,
        monitorView: showMonitorView,
        relatedTopology: showRelatedTopology,
        assetInfo: showAssetInfo,
      }),
    [
      options.includeActionRecords,
      showAssetInfo,
      showMonitorView,
      showRelatedTopology,
      t,
    ],
  );

  return {
    objects,
    tabs,
    showObjectSwitcher: objects.length > 1 && (showMonitorView || showRelatedTopology || showAssetInfo),
    monitorView: {
      visible: showMonitorView,
      loadWidget: monitorView.loadWidget,
      active: options.activeTab === 'monitorView',
    },
    relatedTopology: {
      visible: showRelatedTopology,
      loadWidget: relatedTopology.loadWidget,
      active: options.activeTab === 'relatedTopology',
    },
    assetInfo: {
      visible: showAssetInfo,
      loadWidget: assetInfo.loadWidget,
      active: options.activeTab === 'assetInfo',
    },
  };
}

export function AlarmObjectSwitcher({
  objects,
  value,
  onChange,
}: {
  objects: AlarmSnapshotObject[];
  value: string;
  onChange: (key: string) => void;
}) {
  if (objects.length <= 1) {
    return null;
  }
  return (
    <Select
      className="w-[240px]"
      value={value}
      options={objects.map((item) => ({
        value: item.key,
        label: item.label,
      }))}
      onChange={onChange}
    />
  );
}

function useActiveBoundIdentifier(identifier: string, active: boolean) {
  const [bound, setBound] = useState(identifier);
  useEffect(() => {
    if (active) {
      setBound(identifier);
    }
  }, [active, identifier]);
  return bound;
}

export function PublicWidgetPane({
  active,
  loadWidget,
  identifier,
  identifierProp,
  toolbarStart,
}: {
  active: boolean;
  loadWidget: (() => Promise<{ default: unknown }>) | null;
  identifier: string;
  identifierProp: 'instUuid' | 'monitorId';
  toolbarStart?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const boundIdentifier = useActiveBoundIdentifier(identifier, active);
  const [loadEpoch, setLoadEpoch] = useState(0);
  const [headerAction, setHeaderAction] = useState<React.ReactNode>(null);
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget,
    active: active && Boolean(identifier),
    reloadKey: loadEpoch,
  });

  useEffect(() => {
    setHeaderAction(null);
  }, [boundIdentifier]);

  const missingIdentifier = (active && !identifier) || !boundIdentifier;
  const hasContent = Boolean(Widget) && !loadFailed && !missingIdentifier;
  const showToolbar = Boolean(toolbarStart) || Boolean(headerAction);

  let body: React.ReactNode;
  if (missingIdentifier) {
    body = <CompactEmptyState description={t('alarms.missingStableId')} />;
  } else if (loadFailed) {
    body = (
      <div className="flex flex-col items-center justify-center gap-3 text-[var(--color-text-3)]">
        <span>{t('common.loadFailed')}</span>
        <Button onClick={() => setLoadEpoch((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  } else if (!Widget) {
    body = <Spin />;
  } else if (identifierProp === 'instUuid') {
    body = (
      <InstUuidMount
        key={boundIdentifier}
        Widget={Widget as InstUuidWidget}
        instUuid={boundIdentifier}
        onHeaderAction={setHeaderAction}
      />
    );
  } else {
    body = (
      <MonitorIdMount
        key={boundIdentifier}
        Widget={Widget as MonitorIdWidget}
        monitorId={boundIdentifier}
      />
    );
  }

  return (
    <div className="flex h-full min-h-[280px] min-w-0 flex-1 flex-col gap-4">
      {showToolbar ? (
        <div className="flex shrink-0 items-center justify-between gap-3">
          <div className="min-w-0 flex-1">{toolbarStart}</div>
          {headerAction ? <div className="shrink-0">{headerAction}</div> : null}
        </div>
      ) : null}
      <div
        className={
          hasContent
            ? 'min-h-0 min-w-0 flex-1 overflow-auto'
            : 'flex min-h-0 min-w-0 flex-1 items-center justify-center'
        }
      >
        {body}
      </div>
    </div>
  );
}

function InstUuidMount({
  Widget,
  instUuid,
  onHeaderAction,
}: {
  Widget: InstUuidWidget;
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
}) {
  return <Widget instUuid={instUuid} onHeaderAction={onHeaderAction} />;
}

function MonitorIdMount({
  Widget,
  monitorId,
}: {
  Widget: MonitorIdWidget;
  monitorId: string;
}) {
  return <Widget monitorId={monitorId} />;
}
