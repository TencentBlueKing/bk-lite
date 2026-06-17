'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import {
  UserItem,
  Organization,
  UnitListItem,
  GroupedUnitList,
} from '@/app/monitor/types';
import Spin from '@/components/spin';
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
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const { isLoading } = useApiClient();
  const commonContext = useUserInfoContext();
  const { getAllUsers, getUnitList } = monitorApi();
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [unitList, setUnitList] = useState<UnitListItem[]>([]);
  const [groupedUnitList, setGroupedUnitList] = useState<GroupedUnitList[]>([]);
  const [pageLoading, setPageLoading] = useState(false);

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
    setPageLoading(true);
    try {
      const { users, units, groupedUnits } = await loadMonitorCommonData({
        getAllUsers,
        getUnitList,
      });
      setUserList(users);
      setUnitList(units);
      setGroupedUnitList(groupedUnits);
    } finally {
      setPageLoading(false);
    }
  };
  return pageLoading ? (
    <Spin />
  ) : (
    <CommonContext.Provider
      value={{
        userList,
        unitList,
        groupedUnitList,
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
