'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Select, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { useAppWidget, useLazyAppWidget } from '@/context/appCapabilities';
import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';
import {
  alarmHasAnyInstUuid,
  alarmHasAnyMonitorId,
  alarmHasAnyNodeId,
  listAlarmSnapshotObjects,
  type AlarmSnapshotObject,
} from '@/app/alarm/utils/alarmSnapshotObjects';
import { buildAlarmDetailPublicTabs } from '@/app/alarm/utils/alarmDetailPublicTabs';
import { resolveAlarmPublicWidgetVisibility } from '@/app/alarm/utils/alarmPublicWidgetVisibility';

type IdentifierProp =
  | 'instUuid'
  | 'monitorId'
  | 'logAlertId'
  | 'nodeId'
  | 'serviceId';

type InstUuidWidget = React.ComponentType<{
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
  onEmbedToolbar?: (toolbar: React.ReactNode) => void;
  objectSwitcher?: React.ReactNode;
}>;
type IdentifierWidget = React.ComponentType<Record<string, string>>;

export function useAlarmPublicWidgets(options: {
  monitorObjects?: MonitorObjectSnapshot[];
  includeActionRecords: boolean;
  activeTab: string;
  logAlertId?: string;
  serviceId?: string;
}) {
  const alertRawLog = useAppWidget('log.alertRawLog');
  const monitorView = useAppWidget('monitor.monitorView');
  const relatedTopology = useAppWidget('ops-analysis.relatedTopology');
  const assetInfo = useAppWidget('cmdb.baseInfo');
  const assetChange = useAppWidget('cmdb.assetChange');
  const nodeStatus = useAppWidget('node.nodeStatus');
  const serviceOverview = useAppWidget('apm.serviceOverview');
  const callChain = useAppWidget('apm.callChain');
  const objects = useMemo(
    () => listAlarmSnapshotObjects(options.monitorObjects),
    [options.monitorObjects],
  );
  const visibility = resolveAlarmPublicWidgetVisibility({
    alertRawLogDeclared: alertRawLog.declared,
    monitorViewDeclared: monitorView.declared,
    relatedTopologyDeclared: relatedTopology.declared,
    assetInfoDeclared: assetInfo.declared,
    assetChangeDeclared: assetChange.declared,
    nodeStatusDeclared: nodeStatus.declared,
    serviceOverviewDeclared: serviceOverview.declared,
    callChainDeclared: callChain.declared,
    hasLogAlertId: Boolean(options.logAlertId),
    hasMonitorId: alarmHasAnyMonitorId(options.monitorObjects),
    hasInstUuid: alarmHasAnyInstUuid(options.monitorObjects),
    hasNodeId: alarmHasAnyNodeId(options.monitorObjects),
    hasServiceId: Boolean(options.serviceId),
  });

  const { t } = useTranslation();
  const tabs = useMemo(
    () =>
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: options.includeActionRecords,
        ...visibility,
      }),
    [options.includeActionRecords, t, visibility],
  );

  const showObjectSwitcher =
    objects.length > 1 &&
    (visibility.monitorView ||
      visibility.relatedTopology ||
      visibility.assetInfo ||
      visibility.assetChange ||
      visibility.nodeStatus);

  return {
    objects,
    tabs,
    showObjectSwitcher,
    alertRawLog: {
      visible: visibility.alertRawLog,
      loadWidget: alertRawLog.loadWidget,
      active: options.activeTab === 'alertRawLog',
    },
    monitorView: {
      visible: visibility.monitorView,
      loadWidget: monitorView.loadWidget,
      active: options.activeTab === 'monitorView',
    },
    relatedTopology: {
      visible: visibility.relatedTopology,
      loadWidget: relatedTopology.loadWidget,
      active: options.activeTab === 'relatedTopology',
    },
    assetInfo: {
      visible: visibility.assetInfo,
      loadWidget: assetInfo.loadWidget,
      active: options.activeTab === 'assetInfo',
    },
    assetChange: {
      visible: visibility.assetChange,
      loadWidget: assetChange.loadWidget,
      active: options.activeTab === 'assetChange',
    },
    nodeStatus: {
      visible: visibility.nodeStatus,
      loadWidget: nodeStatus.loadWidget,
      active: options.activeTab === 'nodeStatus',
    },
    serviceOverview: {
      visible: visibility.serviceOverview,
      loadWidget: serviceOverview.loadWidget,
      active: options.activeTab === 'serviceOverview',
    },
    callChain: {
      visible: visibility.callChain,
      loadWidget: callChain.loadWidget,
      active: options.activeTab === 'callChain',
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
  identifierProp: IdentifierProp;
  toolbarStart?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const boundIdentifier = useActiveBoundIdentifier(identifier, active);
  const [loadEpoch, setLoadEpoch] = useState(0);
  const [headerAction, setHeaderAction] = useState<React.ReactNode>(null);
  const [embedToolbar, setEmbedToolbar] = useState<React.ReactNode>(null);
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget,
    active: active && Boolean(identifier),
    reloadKey: loadEpoch,
  });

  useEffect(() => {
    setHeaderAction(null);
    setEmbedToolbar(null);
  }, [boundIdentifier]);

  const missingIdentifier = (active && !identifier) || !boundIdentifier;
  const hasContent = Boolean(Widget) && !loadFailed && !missingIdentifier;
  const showHostToolbar =
    !embedToolbar && (Boolean(toolbarStart) || Boolean(headerAction));

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
        onEmbedToolbar={setEmbedToolbar}
        objectSwitcher={toolbarStart}
      />
    );
  } else {
    body = (
      <IdentifierMount
        key={boundIdentifier}
        Widget={Widget as IdentifierWidget}
        identifierProp={identifierProp}
        identifier={boundIdentifier}
      />
    );
  }

  return (
    <div className="flex h-full min-h-[280px] min-w-0 flex-1 flex-col gap-4">
      {embedToolbar ? (
        <div className="w-full shrink-0">{embedToolbar}</div>
      ) : showHostToolbar ? (
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
  onEmbedToolbar,
  objectSwitcher,
}: {
  Widget: InstUuidWidget;
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
  onEmbedToolbar?: (toolbar: React.ReactNode) => void;
  objectSwitcher?: React.ReactNode;
}) {
  return (
    <Widget
      instUuid={instUuid}
      onHeaderAction={onHeaderAction}
      onEmbedToolbar={onEmbedToolbar}
      objectSwitcher={objectSwitcher}
    />
  );
}

function IdentifierMount({
  Widget,
  identifierProp,
  identifier,
}: {
  Widget: IdentifierWidget;
  identifierProp: Exclude<IdentifierProp, 'instUuid'>;
  identifier: string;
}) {
  return <Widget {...{ [identifierProp]: identifier }} />;
}
