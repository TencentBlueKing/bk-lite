'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import { UserItem, ModelItem } from '@/app/cmdb/types/assetManage';
import { useModelApi, useUserConfigApi } from '@/app/cmdb/api';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import Spin from '@/components/spin';
import { usePathname } from 'next/navigation';
import { useAliveController } from 'react-activation';
interface CommonContextType {
  userList: UserItem[];
  modelList: ModelItem[];
  refreshModelList: () => Promise<void>;
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [modelList, setModelList] = useState<ModelItem[]>([]);
  const [pageLoading, setPageLoading] = useState(false);
  const { get } = useApiClient();
  const { getModelList } = useModelApi();
  const { getAllConfigs } = useUserConfigApi();
  const setUserConfigs = useAssetDataStore((state) => state.setUserConfigs);
  const { drop } = useAliveController();
  const pathname = usePathname();

  useEffect(() => {
    if (drop && !pathname.startsWith('/cmdb/assetData')) {
      drop('assetData');
    }
  }, [pathname]);

  const fetchUserList = async () => {
    try {
      const response = await get('/core/api/user_group/user_list/', {
        params: {
          page_size: 10000,
          page: 1,
        },
      });

      const userData: UserItem[] = response.users || [];
      setUserList(userData);
    } catch (error) {
      console.error('Failed to fetch user list:', error);
      setUserList([]);
    }
  };

  const fetchModelList = async () => {
    try {
      const data = await getModelList();
      setModelList(data || []);
    } catch (error) {
      console.error('Failed to fetch model list:', error);
      setModelList([]);
    }
  };

  const fetchUserConfigs = async () => {
    try {
      const configs = await getAllConfigs();
      setUserConfigs(configs);
    } catch (error) {
      console.error('Failed to fetch user configs:', error);
      setUserConfigs({});
    }
  };

  useEffect(() => {
    const initializeData = async () => {
      setPageLoading(true);
      try {
        await Promise.all([fetchUserList(), fetchModelList(), fetchUserConfigs()]);
      } finally {
        setPageLoading(false);
      }
    };

    initializeData();
  }, []);
  return pageLoading ? (
    <Spin></Spin>
  ) : (
    <CommonContext.Provider
      value={{
        userList,
        modelList,
        refreshModelList: fetchModelList,
      }}
    >
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => useContext(CommonContext);

export default CommonContextProvider;
