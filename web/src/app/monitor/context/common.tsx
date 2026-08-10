'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import {
  UserItem,
  Organization,
  UnitListItem,
  GroupedUnitList,
} from '@/app/monitor/types';
import { useUserInfoContext } from '@/context/userInfo';
import { transformTreeData } from '@/app/monitor/utils/common';
import monitorApi from '@/app/monitor/api';
import {
  loadMonitorCommonData,
  shouldLoadMonitorCommonData,
} from './commonDataLoader';

interface CommonContextType {
  userList: UserItem[];
  authOrganizations: Organization[];
  unitList: UnitListItem[];
  groupedUnitList: GroupedUnitList[];
  /** 公共数据后台加载中;集成列表等不依赖方无需等待 */
  commonLoading: boolean;
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const { isLoading } = useApiClient();
  const commonContext = useUserInfoContext();
  const { getAllUsers, getUnitList } = monitorApi();
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [unitList, setUnitList] = useState<UnitListItem[]>([]);
  const [groupedUnitList, setGroupedUnitList] = useState<GroupedUnitList[]>([]);
  const [commonLoading, setCommonLoading] = useState(false);

  useEffect(() => {
    if (!shouldLoadMonitorCommonData({
      requestLoading: isLoading,
      userInfoLoading: commonContext.loading,
      selectedGroupId: commonContext.selectedGroup?.id,
    })) {
      return;
    }
    getPermissionGroups();
  }, [isLoading, commonContext.loading, commonContext.selectedGroup?.id]);

  const getPermissionGroups = async () => {
    setCommonLoading(true);
    try {
      const cacheKey = String(commonContext.selectedGroup?.id ?? '');
      const { users, units, groupedUnits } = await loadMonitorCommonData({
        getAllUsers,
        getUnitList,
        cacheKey,
      });
      setUserList(users);
      setUnitList(units);
      setGroupedUnitList(groupedUnits);
    } finally {
      setCommonLoading(false);
    }
  };

  // 不再用全屏 Spin 挡住子路由:集成列表等可先渲染,公共数据后台补齐
  return (
    <CommonContext.Provider
      value={{
        userList,
        unitList,
        groupedUnitList,
        commonLoading,
        authOrganizations: transformTreeData(
          commonContext?.groups || []
        ) as any,
      }}
    >
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => useContext(CommonContext);

export default CommonContextProvider;
