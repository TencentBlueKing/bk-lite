'use client';
import React, { useEffect, useState, useRef } from 'react';
import List from './list';
import { useModelApi, useInstanceApi, useCollectApi } from '@/app/cmdb/api';
import { useSearchParams } from 'next/navigation';
import { Spin } from 'antd';
import { useCommon } from '@/app/cmdb/context/common';
import {
  ensureCollectTaskMap,
} from '@/app/cmdb/utils/collectTask';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import {
  AttrFieldType,
  UserItem,
  InstDetail,
} from '@/app/cmdb/types/assetManage';

const BaseInfo = () => {
  const { getModelAttrGroupsFullInfo } = useModelApi();
  const { getInstanceDetail } = useInstanceApi();
  const { getCollectTaskNames } = useCollectApi();

  const searchParams = useSearchParams();
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);

  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';
  const [instDetail, setInstDetail] = useState<InstDetail>({});
  const [pageLoading, setPageLoading] = useState<boolean>(false);

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

  return (
    <Spin spinning={pageLoading} className="min-h-[calc(100vh-180px)]">
      {/* propertyList是模型属性列表+值 */}
      <List
        instDetail={instDetail}
        propertyList={propertyList}
        userList={userList}
        onsuccessEdit={onsuccessEdit}
      />
    </Spin>
  );
};
export default BaseInfo;
