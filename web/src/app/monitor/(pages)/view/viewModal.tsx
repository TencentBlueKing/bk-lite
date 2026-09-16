'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
} from 'react';
import { useScreenAwareRouter } from '@/console-layout';
import { Button, Tabs } from 'antd';
import OperateDrawer from '@/components/operate-drawer';
import { ModalRef, TabItem, ChartProps } from '@/app/monitor/types';
import { ViewModalProps } from '@/app/monitor/types/view';
import { useTranslation } from '@/utils/i18n';
import MonitorView from './monitorView';
import MonitorAlarm from './monitorAlarm';
import MonitorPolicy from './monitorPolicy';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';
import { resolveDashboardUrl } from '@/app/monitor/dashboards/registry';
import { withDashboardReturnContext } from '@/app/monitor/dashboards/shared/utils';
import { encodeInstanceIdValuesParam } from '@/app/monitor/dashboards/shared/utils/instance';
import { findByMonitorId } from '@/app/monitor/utils/monitorIds';
import { useAppWidget } from '@/context/appCapabilities';
import useMonitorApi from '@/app/monitor/api';
import { ViewModalPublicPane } from '@/app/monitor/components/public/ViewModalPublicPane';
import {
  buildViewModalLocalTabs,
  readViewModalStableIds,
  resolveViewModalPublicTabs,
  shouldLookupViewModalStableIds,
} from '@/app/monitor/utils/viewModalPublicTabs';

const ViewModal = forwardRef<ModalRef, ViewModalProps>(
  ({ monitorObject, monitorName, plugins, metrics, objects = [] }, ref) => {
    const { t } = useTranslation();
    const router = useScreenAwareRouter();
    const { lookupInstance } = useMonitorApi();
    const lookupInstanceRef = useRef(lookupInstance);
    lookupInstanceRef.current = lookupInstance;
    const relatedTopology = useAppWidget('ops-analysis.relatedTopology');
    const baseInfo = useAppWidget('cmdb.baseInfo');
    const assetChange = useAppWidget('cmdb.assetChange');
    const nodeStatus = useAppWidget('node.nodeStatus');
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [viewConfig, setViewConfig] =
      useState<ChartProps>(INIT_VIEW_MODAL_FORM);
    const [currentTab, setCurrentTab] = useState<string>('monitorView');
    const formIds = readViewModalStableIds(viewConfig as Record<string, unknown>);
    const [lookupIds, setLookupIds] = useState({ instUuid: '', nodeId: '' });
    const instUuid = formIds.instUuid || lookupIds.instUuid;
    const nodeId = formIds.nodeId || lookupIds.nodeId;
    const publicTabs = resolveViewModalPublicTabs({
      instUuid,
      nodeId,
      widgets: {
        'ops-analysis.relatedTopology': relatedTopology.declared,
        'cmdb.baseInfo': baseInfo.declared,
        'cmdb.assetChange': assetChange.declared,
        'node.nodeStatus': nodeStatus.declared,
      },
      t,
    });
    const localTabs = buildViewModalLocalTabs(t);
    const tabs: TabItem[] = [
      ...localTabs,
      ...publicTabs.map((item) => ({ key: item.key, label: item.label })),
    ];
    const identifiers = {
      relatedTopology: instUuid,
      baseInfo: instUuid,
      assetChange: instUuid,
      nodeStatus: nodeId,
    };
    const loaders = {
      relatedTopology: relatedTopology.loadWidget,
      baseInfo: baseInfo.loadWidget,
      assetChange: assetChange.loadWidget,
      nodeStatus: nodeStatus.loadWidget,
    };
    const rightSlot = (
      <Button
        type="link"
        className="relative bottom-0 right-0"
        onClick={() => linkToDetial()}
      >
        {t('monitor.views.viewDashboard')}
      </Button>
    );

    useEffect(() => {
      const monitorId = formIds.monitorId;
      const shouldLookup =
        groupVisible &&
        shouldLookupViewModalStableIds({
          monitorId,
          instUuid: formIds.instUuid,
          nodeId: formIds.nodeId,
          widgets: {
            'ops-analysis.relatedTopology': relatedTopology.declared,
            'cmdb.baseInfo': baseInfo.declared,
            'cmdb.assetChange': assetChange.declared,
            'node.nodeStatus': nodeStatus.declared,
          },
        });
      if (!shouldLookup) {
        if (!groupVisible) setLookupIds({ instUuid: '', nodeId: '' });
        return;
      }
      let cancelled = false;
      lookupInstanceRef
        .current({ instance_id: monitorId })
        .then((lookup) => {
          if (cancelled) return;
          const instance = lookup?.instance as
            | { cmdb_id?: string; node_id?: string }
            | undefined;
          setLookupIds({
            instUuid: String(instance?.cmdb_id || '').trim(),
            nodeId: String(instance?.node_id || '').trim(),
          });
        })
        .catch(() => {
          if (!cancelled) setLookupIds({ instUuid: '', nodeId: '' });
        });
      return () => {
        cancelled = true;
      };
    }, [
      assetChange.declared,
      baseInfo.declared,
      formIds.instUuid,
      formIds.monitorId,
      formIds.nodeId,
      groupVisible,
      nodeStatus.declared,
      relatedTopology.declared,
    ]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setGroupVisible(true);
        setTitle(title);
        setViewConfig(form as ChartProps);
        setLookupIds({ instUuid: '', nodeId: '' });
      },
    }));

    const changeTab = (val: string) => {
      setCurrentTab(val);
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setCurrentTab('monitorView');
      setViewConfig(INIT_VIEW_MODAL_FORM);
      setLookupIds({ instUuid: '', nodeId: '' });
    };

    const linkToDetial = () => {
      const monitorItem = findByMonitorId(objects, monitorObject);
      const row: Record<string, string> = {
        monitorObjId: String(monitorObject || ''),
        name: monitorName,
        monitorObjDisplayName: monitorItem?.display_name || '',
        icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
        instance_id: String(viewConfig.instance_id || ''),
        instance_name: String(viewConfig.instance_name || ''),
        instance_id_values: encodeInstanceIdValuesParam(
          viewConfig.instance_id_values
        ),
        instance_id_keys: Array.isArray(viewConfig.instance_id_keys) && viewConfig.instance_id_keys.length
          ? viewConfig.instance_id_keys.join(',')
          : Array.isArray(monitorItem?.instance_id_keys)
            ? monitorItem.instance_id_keys.join(',')
            : 'instance_id'
      };
      const params = withDashboardReturnContext(new URLSearchParams(row), {
        objectId: String(monitorObject || ''),
        objectName: String(monitorItem?.display_name || monitorItem?.name || '')
      });
      const instancePlugins = Array.isArray(viewConfig.plugins)
        ? viewConfig.plugins
        : undefined;
      const professionalDashboardUrl = resolveDashboardUrl({
        monitorObjectName: monitorName,
        monitorObjectDisplayName: monitorItem?.display_name,
        instancePlugins,
        queryString: params.toString(),
      });
      const targetUrl = professionalDashboardUrl || `/monitor/view/detail?${params.toString()}`;
      router.push(targetUrl);
    };

    return (
      <div>
        <OperateDrawer
          width={950}
          title={title}
          subTitle={viewConfig.instance_name}
          visible={groupVisible}
          destroyOnHidden
          classNames={{
            body: 'flex min-h-0 flex-col overflow-hidden',
          }}
          styles={{
            body: { overflow: 'hidden' },
          }}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
          onClose={handleCancel}
        >
          <Tabs
            className="shrink-0"
            activeKey={currentTab}
            items={tabs}
            onChange={changeTab}
            tabBarExtraContent={rightSlot}
          />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            {currentTab === 'monitorView' ? (
              <div className="min-h-0 flex-1 overflow-auto">
                <MonitorView
                  monitorObject={monitorObject}
                  monitorName={monitorName}
                  plugins={plugins}
                  form={viewConfig}
                />
              </div>
            ) : null}
            {currentTab === 'alertList' ? (
              <div className="min-h-0 flex-1 overflow-auto">
                <MonitorAlarm
                  monitorObject={monitorObject}
                  monitorName={monitorName}
                  plugins={plugins}
                  form={viewConfig}
                  metrics={metrics}
                  objects={objects}
                />
              </div>
            ) : null}
            {currentTab === 'monitorPolicy' ? (
              <div className="min-h-0 flex-1 overflow-auto">
                <MonitorPolicy
                  monitorObject={monitorObject}
                  monitorName={monitorName}
                  plugins={plugins}
                  form={viewConfig}
                  objects={objects}
                />
              </div>
            ) : null}
            {publicTabs.map((item) => (
              <div
                key={item.key}
                className={
                  currentTab === item.key
                    ? 'flex h-full min-h-0 flex-1 flex-col overflow-hidden'
                    : 'hidden'
                }
              >
                <ViewModalPublicPane
                  active={currentTab === item.key}
                  loadWidget={loaders[item.key]}
                  identifier={identifiers[item.key]}
                  identifierProp={item.identifierProp}
                />
              </div>
            ))}
          </div>
        </OperateDrawer>
      </div>
    );
  }
);
ViewModal.displayName = 'ViewModal';
export default ViewModal;
