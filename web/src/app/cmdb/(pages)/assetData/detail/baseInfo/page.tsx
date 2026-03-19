'use client';
import React, { useEffect, useState, useRef } from 'react';
import List from './list';
import { useModelApi, useInstanceApi, useCollectApi } from '@/app/cmdb/api';
import { useSearchParams } from 'next/navigation';
import { Spin, Modal, Button, Space } from 'antd';
import { useCommon } from '@/app/cmdb/context/common';
import {
  ensureCollectTaskMap,
} from '@/app/cmdb/utils/collectTask';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import { useUserInfoContext } from '@/context/userInfo';
import SubscriptionDrawer from '@/app/cmdb/components/subscription/SubscriptionDrawer';
import SubscriptionRuleForm, { type SubscriptionRuleFormRef } from '@/app/cmdb/components/subscription/SubscriptionRuleForm';
import { useQuickSubscribeDefaults, useSubscriptionMutation } from '@/app/cmdb/hooks/useSubscription';
import { useTranslation } from '@/utils/i18n';
import {
  AttrFieldType,
  UserItem,
  InstDetail,
} from '@/app/cmdb/types/assetManage';

const BaseInfo = () => {
  const { t } = useTranslation();
  const { getModelAttrGroupsFullInfo } = useModelApi();
  const { getInstanceDetail } = useInstanceApi();
  const { getCollectTaskNames } = useCollectApi();

  const searchParams = useSearchParams();
  const { selectedGroup, userId } = useUserInfoContext();
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [subscriptionDrawerOpen, setSubscriptionDrawerOpen] = useState(false);
  const [quickSubscribeModalOpen, setQuickSubscribeModalOpen] = useState(false);
  const quickSubscribeFormRef = useRef<SubscriptionRuleFormRef>(null);
  const { submitting: quickSubscribeSubmitting, createRule: quickSubscribeCreateRule } = useSubscriptionMutation();

  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';
  const modelName: string = searchParams.get('model_name') || '';
  const instName: string = searchParams.get('inst_name') || searchParams.get('ip_addr') || '--';
  const [instDetail, setInstDetail] = useState<InstDetail>({});
  const [pageLoading, setPageLoading] = useState<boolean>(false);

  const quickDefaults = useQuickSubscribeDefaults('detail', {
    model_id: modelId,
    model_name: modelName,
    currentInstanceId: Number(instId || 0),
    currentInstanceName: instName,
    currentUser: Number(userId || userList[0]?.id || 0),
    currentOrganization: Number(selectedGroup?.id || 0),
  });

  useEffect(() => {
    getInitData();
  }, []);

  useEffect(() => {
    // Given 详情页也支持 collect_task 跳转，When 页面进入，Then 预热与列表页一致的映射缓存。
    ensureCollectTaskMap(getCollectTaskNames).catch(() => {
      const store = useAssetDataStore.getState();
      store.setCollectTaskMap({});
      store.setCollectTaskRouteMap({});
      store.setCollectTaskOptions([]);
    });
  }, []);

  const getInitData = async () => {
    setPageLoading(true);
    try {

      // 通过Promise.all并发获取模型属性列表和实例详情
      const [propertData, instDetailData] = await Promise.all([
        // getModelAttrList(modelId),
        getModelAttrGroupsFullInfo(modelId),
        getInstanceDetail(instId),
      ]);

      // 模型属性列表+值：propertData.groups
      // console.log("test7.5", propertData.groups);

      setPropertyList(propertData.groups);
      setInstDetail(instDetailData);
    } catch {
      console.log('获取数据失败');
    } finally {
      setPageLoading(false);
    }
  };

  const onsuccessEdit = async () => {
    setPageLoading(true);
    try {
      const data = await getInstanceDetail(instId);
      setInstDetail(data);
    } finally {
      setPageLoading(false);
    }
  };

  const handleQuickSubscribeSubmit = async (payload: any, enabled: boolean) => {
    await quickSubscribeCreateRule({ ...payload, is_enabled: enabled });
    setQuickSubscribeModalOpen(false);
  };

  return (
    <Spin spinning={pageLoading} className="min-h-[calc(100vh-180px)]">
      {/* propertyList是模型属性列表+值 */}
      <List
        instDetail={instDetail}
        propertyList={propertyList}
        userList={userList}
        onsuccessEdit={onsuccessEdit}
        onSubscribe={() => setQuickSubscribeModalOpen(true)}
      />
      <SubscriptionDrawer
        open={subscriptionDrawerOpen}
        onClose={() => setSubscriptionDrawerOpen(false)}
        modelId={modelId}
        modelName={modelName}
        quickDefaults={quickDefaults}
      />
      <Modal
        open={quickSubscribeModalOpen}
        width={800}
        title={t('subscription.createRule')}
        centered
        onCancel={() => setQuickSubscribeModalOpen(false)}
        footer={(
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button
              type="primary"
              loading={quickSubscribeSubmitting}
              onClick={() => void quickSubscribeFormRef.current?.submit(true)}
            >
              {t('subscription.saveAndEnable')}
            </Button>
            <Button
              loading={quickSubscribeSubmitting}
              onClick={() => void quickSubscribeFormRef.current?.submit(false)}
            >
              {t('subscription.saveOnly')}
            </Button>
            <Button onClick={() => setQuickSubscribeModalOpen(false)}>
              {t('subscription.cancel')}
            </Button>
          </Space>
        )}
        destroyOnClose
        styles={{
          body: {
            maxHeight: 'calc(100vh - 220px)',
            overflowY: 'auto',
            paddingTop: 24,
            paddingLeft: 24,
            paddingRight: 24,
          },
        }}
      >
        <SubscriptionRuleForm
          ref={quickSubscribeFormRef}
          quickDefaults={quickDefaults}
          modelId={modelId}
          modelName={modelName}
          onSubmitAndEnable={(data) => handleQuickSubscribeSubmit(data, true)}
          onSubmitOnly={(data) => handleQuickSubscribeSubmit(data, false)}
        />
      </Modal>
    </Spin>
  );
};
export default BaseInfo;
