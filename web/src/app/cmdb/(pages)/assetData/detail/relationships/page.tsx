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
import NetworkTopo from './networkTopo';
import RackElevation from './rackElevation';
import RoomFloorPlan from './roomFloorPlan';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useCommon } from '@/app/cmdb/context/common';
import { useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { useRelationships } from '@/app/cmdb/context/relationships';

const Ralationships = () => {
  const { t } = useTranslation();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const { modelList, assoTypes, loading } = useRelationships();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const assoListRef = useRef<AssoListRef>(null);
  const [isExpand, setIsExpand] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<string>(
    searchParams.get('tab') || 'list'
  );
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';
  const tabParam: string = searchParams.get('tab') || '';

  const { getTopoThemes } = useInstanceApi();
  const [themes, setThemes] = useState<string[]>([]);

  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    getTopoThemes(modelId)
      .then((res: { themes: string[] }) => {
        if (!cancelled) setThemes(res?.themes || []);
      })
      .catch(() => {
        if (!cancelled) setThemes([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId]);

  // 下钻进入时若带 tab 参数（如机房视图点机柜跳到机柜的「机柜视图」），自动选中该 Tab
  useEffect(() => {
    if (tabParam) setActiveTab(tabParam);
  }, [tabParam, instId]);

  const segmentedOptions = [
    { label: t('list'), value: 'list' },
    { label: t('topo'), value: 'topo' },
    ...(themes.includes('network')
      ? [{ label: t('Model.networkTopo'), value: 'network' }]
      : []),
    ...(modelId === 'rack'
      ? [{ label: t('Model.rackElevation'), value: 'rackView' }]
      : []),
    ...(modelId === 'server_room'
      ? [{ label: t('Model.roomLayout'), value: 'roomView' }]
      : []),
  ];

  const handleTabChange = (val: string) => {
    setActiveTab(val);
    setIsExpand(true);
  };

  const handleExpand = () => {
    assoListRef.current?.expandAll(!isExpand);
    setIsExpand(!isExpand);
  };

  const handleRelate = () => {
    assoListRef.current?.showRelateModal();
  };

  return (
    <Spin spinning={loading}>
      <header className={relationshipsStyle.header}>
        <Segmented
          className="mb-[10px]"
          value={activeTab}
          options={segmentedOptions}
          onChange={handleTabChange}
        />
        {activeTab === 'list' && (
          <div className={relationshipsStyle.operation}>
            <PermissionWrapper requiredPermissions={['Add Associate']}>
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
      {activeTab === 'list' && (
        <AssoList
          ref={assoListRef}
          userList={userList}
          modelList={modelList}
          assoTypeList={assoTypes}
        />
      )}
      {activeTab === 'topo' && (
        <Topo
          assoTypeList={assoTypes}
          modelList={modelList}
          modelId={modelId}
          instId={instId}
        />
      )}
      {activeTab === 'network' && (
        <NetworkTopo modelId={modelId} instId={instId} />
      )}
      {activeTab === 'rackView' && (
        <RackElevation modelId={modelId} instId={instId} />
      )}
      {activeTab === 'roomView' && (
        <RoomFloorPlan modelId={modelId} instId={instId} />
      )}
    </Spin>
  );
};

export default Ralationships;
