'use client';
import React, { useState, useRef } from 'react';
import Icon from '@/components/icon';
import {
  UserItem,
  Organization,
  AssoListRef,
} from '@/app/cmdb/types/assetManage';
import { Segmented, Button, Spin } from 'antd';
import { GatewayOutlined } from '@ant-design/icons';
import relationshipsStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import AssoList from './list';
import Topo from './topo';
import { useCommon } from '@/app/cmdb/context/common';
import { useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { useRelationships } from '@/app/cmdb/context/relationships';

const Ralationships = () => {
  const { t } = useTranslation();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const { modelList, assoTypes, loading } = useRelationships();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const assoListRef = useRef<AssoListRef>(null);
  const [isExpand, setIsExpand] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<string>('list');
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';

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
          options={[
            {
              label: t('list'),
              value: 'list',
            },
            {
              label: t('topo'),
              value: 'topo',
            },
          ]}
          onChange={handleTabChange}
        />
        {activeTab === 'list' && (
          <div className={relationshipsStyle.operation}>
            <PermissionWrapper requiredPermissions={['Add']}>
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
      {activeTab === 'list' ? (
        <AssoList
          ref={assoListRef}
          userList={userList}
          organizationList={organizationList}
          modelList={modelList}
          assoTypeList={assoTypes}
        />
      ) : (
        <Topo
          assoTypeList={assoTypes}
          modelList={modelList}
          modelId={modelId}
          instId={instId}
        />
      )}
    </Spin>
  );
};

export default Ralationships;
