'use client';

import { useCallback, useEffect, useRef, useState, type Key } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { overviewHostAlertParams, readAlertCount } from '../../host/layered/host-alert-list';
import host from '../../host/layered/layered.module.scss';
import pageStyles from '../index.module.scss';
import DockerContainersPane from './containers-pane';
import { dockerText, type DockerCopyKey } from './copy';
import DockerOverviewPane from './overview-pane';
import { useDockerPro } from './use-docker-pro';

interface DockerCategoryLayoutProps {
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  intervalSec?: number;
  reloadKey: number;
}

type DockerTab = 'overview' | 'containers';

export default function DockerCategoryLayout({
  instanceId,
  monitorObjectId,
  idValues,
  instanceIdKeys,
  timeValues,
  queryTimeRange,
  intervalSec,
  reloadKey
}: DockerCategoryLayoutProps) {
  const { t } = useDashboardText();
  const text = (key: DockerCopyKey) => dockerText(t, key);
  const { getMonitorAlert } = useMonitorApi();
  const pro = useDockerPro({
    instanceId,
    monitorObjectId,
    idValues,
    instanceIdKeys,
    timeValues,
    intervalSec,
    reloadKey
  });
  const [tab, setTab] = useState<DockerTab>('overview');
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [alertDrawerOpen, setAlertDrawerOpen] = useState(false);
  const alertDrawerOpenRef = useRef(false);
  alertDrawerOpenRef.current = alertDrawerOpen;
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const instanceKey = String(instanceId || '');
  const [seenInstance, setSeenInstance] = useState(instanceKey);
  if (instanceKey !== seenInstance) {
    setSeenInstance(instanceKey);
    setAlertCount(null);
  }
  const showContainers = pro.phase === 'ready' && pro.view.containersVisible;
  const activeTab: DockerTab = tab === 'containers' && showContainers ? 'containers' : 'overview';
  const openAlerts = useCallback(() => {
    setAlertDrawerOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);

  useEffect(() => {
    if (activeTab !== 'overview') return undefined;
    if (!instanceKey) {
      setAlertCount(null);
      return undefined;
    }
    let active = true;
    getMonitorAlert(overviewHostAlertParams(instanceKey))
      .then((data) => {
        if (!active || alertDrawerOpenRef.current) return;
        setAlertCount(readAlertCount(data, 0));
      })
      .catch(() => {
        if (!active || alertDrawerOpenRef.current) return;
        setAlertCount(null);
      });
    return () => {
      active = false;
    };
  }, [activeTab, getMonitorAlert, instanceKey, reloadKey]);

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange} suspend={false}>
      <div className={`${host.root} ${pageStyles.fitContent}`} data-docker-pro="category">
        <div className={host.tabBand}>
          <Tabs
            className={host.partitionTabs}
            activeKey={activeTab}
            onChange={(key) => setTab(key === 'containers' ? 'containers' : 'overview')}
            items={[
              { key: 'overview', label: <span data-docker-tab="overview">{text('tabOverview')}</span> },
              ...(showContainers ? [{
                key: 'containers',
                label: <span data-docker-tab="containers">{text('tabContainers')}</span>
              }] : [])
            ]}
          />
        </div>
        <div className={host.main}>
          {activeTab === 'overview' ? (
            <DockerOverviewPane
              phase={pro.phase}
              view={pro.view}
              alertCount={alertCount}
              alertsOpen={alertDrawerOpen}
              onOpenAlerts={openAlerts}
            />
          ) : pro.view ? (
            <DockerContainersPane view={pro.view} />
          ) : null}
        </div>
        <HostAlertDrawer
          open={alertDrawerOpen}
          refreshKey={alertRefreshKey}
          instanceId={instanceKey}
          monitorObjectId={monitorObjectId}
          onClose={() => setAlertDrawerOpen(false)}
          onCount={setAlertCount}
          title={text('alertDrawerTitle')}
          footerHint={text('alertDrawerFooter')}
          emptyCopy={text('alertDrawerEmpty')}
          emptyHint={text('alertDrawerEmptyHint')}
        />
      </div>
    </ProTimeWindowProvider>
  );
}
