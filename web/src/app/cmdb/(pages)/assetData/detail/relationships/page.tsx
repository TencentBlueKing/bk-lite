'use client';
import React, { useState, useRef, useEffect } from 'react';
import Icon from '@/components/icon';
import {
  UserItem,
  AssoListRef,
} from '@/app/cmdb/types/assetManage';
import { Segmented, Button, Spin } from 'antd';
import { GatewayOutlined } from '@ant-design/icons';
import relationshipsStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import AssoList from './list';
import Topo from './topo';
import { PublicRelatedTopoSlot } from './publicRelatedTopoSlot';
import {
  canShowNetworkStatusTopoTab,
  PublicNetworkStatusTopoSlot,
} from './publicNetworkStatusTopoSlot';
import NetworkTopo from './networkTopo';
import RackElevation from './rackElevation';
import RoomFloorPlan from './roomFloorPlan';
import ApplicationResourceOverview from './applicationResourceOverview';
import DeviceDetailDrawer from './deviceDetailDrawer';
import IpamMatrix from '../ipView/ipamMatrix';
import type { RackDevice } from '@/app/cmdb/types/rackRoom';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useCmdbUserList } from '@/app/cmdb/context/common';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { useRelationships } from '@/app/cmdb/context/relationships';
import { useAppWidget } from '@/context/appCapabilities';
import usePermissions from '@/hooks/usePermissions';
import {
  buildRelationshipTabHref,
  DEFAULT_RELATIONSHIP_TAB,
  isAllowedRelationshipTab,
  normalizeRelationshipTab,
  relationshipGatesSettled,
} from '../../relationshipViewNavigation';
import {
  RACK_ROOM_ASSET_PERMISSION_PATH,
  canUnplaceFromLayout,
  hasInstanceOperate,
} from './rackRoomEdit';

const Ralationships = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const { modelList, assoTypes, loading } = useRelationships();
  const userList: UserItem[] = useCmdbUserList();
  const assoListRef = useRef<AssoListRef>(null);
  const [isExpand, setIsExpand] = useState<boolean>(false);
  const modelId: string = searchParams.get('model_id') || '';
  const instUuid: string = searchParams.get('inst_uuid') || '';
  const tabParam: string = searchParams.get('tab') || '';

  const { getTopoThemes } = useInstanceApi();
  const [themes, setThemes] = useState<string[]>([]);
  const [themesReady, setThemesReady] = useState(false);
  const networkStatus = useAppWidget('ops-analysis.networkStatusTopology');
  const showNetworkStatusTab = canShowNetworkStatusTopoTab({
    hasNetworkTheme: themes.includes('network'),
    declared: networkStatus.declared,
    instUuid,
  });
  // 机柜视图点设备：右侧抽屉展示详情（再从抽屉下钻到实例详情），与机房视图一致
  const [device, setDevice] = useState<RackDevice | null>(null);
  const [devOpen, setDevOpen] = useState<boolean>(false);
  const [rackNonce, setRackNonce] = useState(0);
  const { hasPermission } = usePermissions(RACK_ROOM_ASSET_PERMISSION_PATH);
  const hasEdit = hasPermission(['Edit']);

  useEffect(() => {
    if (!modelId) {
      setThemes([]);
      setThemesReady(true);
      return;
    }
    let cancelled = false;
    setThemes([]);
    setThemesReady(false);
    getTopoThemes(modelId)
      .then((res: { themes: string[] }) => {
        if (!cancelled) {
          setThemes(res?.themes || []);
          setThemesReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setThemes([]);
          setThemesReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  const segmentedOptions = [
    { label: t('list'), value: 'list' },
    { label: t('topo'), value: 'topo' },
    ...(themes.includes('network')
      ? [{ label: t('Model.networkTopo'), value: 'network' }]
      : []),
    ...(showNetworkStatusTab
      ? [{
        label: t('Model.publicNetworkStatusTopology'),
        value: 'networkStatusTopology',
      }]
      : []),
    ...(themes.includes('ipam')
      ? [{ label: t('Model.ipView'), value: 'ipam' }]
      : []),
    ...(themes.includes('app_overview')
      ? [{ label: t('Model.applicationResourceOverview'), value: 'appOverview' }]
      : []),
    ...(modelId === 'rack'
      ? [{ label: t('Model.rackElevation'), value: 'rackView' }]
      : []),
    ...(modelId === 'server_room'
      ? [{ label: t('Model.roomLayout'), value: 'roomView' }]
      : []),
  ];

  const allowedTabs = segmentedOptions.map((option) => option.value);
  const gatesSettled = relationshipGatesSettled({
    themesReady,
    widgetStatus: networkStatus.status,
  });
  const { tab: activeTab, shouldRewrite } = normalizeRelationshipTab({
    requestedTab: tabParam || DEFAULT_RELATIONSHIP_TAB,
    allowedTabs,
    gatesSettled,
  });

  useEffect(() => {
    if (!shouldRewrite) {
      return;
    }
    router.replace(
      buildRelationshipTabHref(pathname, searchParams, activeTab),
    );
  }, [shouldRewrite, activeTab, pathname, searchParams, router]);

  const handleTabChange = (val: string) => {
    setIsExpand(false);
    router.replace(buildRelationshipTabHref(pathname, searchParams, val));
  };

  const handleExpand = () => {
    assoListRef.current?.expandAll(!isExpand);
  };

  const handleRelate = () => {
    assoListRef.current?.showRelateModal();
  };

  const isCanvasTab = [
    'network',
    'networkStatusTopology',
    'ipam',
    'appOverview',
    'rackView',
    'roomView',
  ].includes(activeTab);

  return (
    <Spin spinning={loading} wrapperClassName={isCanvasTab ? relationshipsStyle.pageSpin : undefined}>
      <div className={isCanvasTab ? relationshipsStyle.pageFill : undefined}>
      <header
        className={`${relationshipsStyle.header}${isCanvasTab ? ` ${relationshipsStyle.headerCanvas}` : ''}`}
      >
        <Segmented
          className="mb-0"
          value={activeTab}
          options={segmentedOptions}
          onChange={handleTabChange}
        />
        {activeTab === 'list' && (
          <div className={relationshipsStyle.operation}>
            <PermissionWrapper
              requiredPermissions={['Add Associate']}
              permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}
            >
              <Button
                type="link"
                icon={<GatewayOutlined />}
                onClick={handleRelate}
              >
                {t('Model.association')}
              </Button>
            </PermissionWrapper>
            <div className={relationshipsStyle.expand} onClick={handleExpand}>
              <Icon
                type={isExpand ? 'a-yijianshouqi1' : 'a-yijianzhankai1'}
              ></Icon>
              <span className={relationshipsStyle.expandText}>
                {isExpand ? t('closeAll') : t('expandAll')}
              </span>
            </div>
          </div>
        )}
      </header>
      <div className={isCanvasTab ? relationshipsStyle.canvasBody : undefined}>
      {activeTab === 'list' && isAllowedRelationshipTab('list', allowedTabs) && (
        <AssoList
          ref={assoListRef}
          userList={userList}
          modelList={modelList}
          assoTypeList={assoTypes}
          onExpandStateChange={setIsExpand}
        />
      )}
      {activeTab === 'topo' && isAllowedRelationshipTab('topo', allowedTabs) && (
        <PublicRelatedTopoSlot
          instUuid={instUuid}
          fallback={
            <Topo
              assoTypeList={assoTypes}
              modelList={modelList}
              modelId={modelId}
              instUuid={instUuid}
            />
          }
        />
      )}
      {activeTab === 'network' && isAllowedRelationshipTab('network', allowedTabs) && (
        <NetworkTopo key={instUuid} modelId={modelId} instUuid={instUuid} fillContainer />
      )}
      {showNetworkStatusTab && activeTab === 'networkStatusTopology' && (
        <PublicNetworkStatusTopoSlot instUuid={instUuid} />
      )}
      {activeTab === 'ipam' && isAllowedRelationshipTab('ipam', allowedTabs) && (
        <div className={relationshipsStyle.scrollCanvas}>
          <IpamMatrix instUuid={instUuid} />
        </div>
      )}
      {activeTab === 'appOverview' && isAllowedRelationshipTab('appOverview', allowedTabs) && (
        <ApplicationResourceOverview modelId={modelId} instUuid={instUuid} fillContainer />
      )}
      {activeTab === 'rackView' && isAllowedRelationshipTab('rackView', allowedTabs) && (
        <div className={relationshipsStyle.scrollCanvas}>
          <RackElevation
            key={`${instUuid}-${rackNonce}`}
            modelId={modelId}
            instUuid={instUuid}
            onDeviceClick={(d) => {
              setDevice(d);
              setDevOpen(true);
            }}
          />
        </div>
      )}
      {activeTab === 'roomView' && isAllowedRelationshipTab('roomView', allowedTabs) && (
        <div className={relationshipsStyle.scrollCanvas}>
          <RoomFloorPlan modelId={modelId} instUuid={instUuid} />
        </div>
      )}
      </div>
      <DeviceDetailDrawer
        device={device}
        open={devOpen}
        onClose={() => setDevOpen(false)}
        containerInstUuid={instUuid}
        canUnplace={canUnplaceFromLayout({
          hasEdit,
          instOperate: hasInstanceOperate(device?.permission),
        })}
        onUnplaced={() => setRackNonce((n) => n + 1)}
      />
      </div>
    </Spin>
  );
};

export default Ralationships;
