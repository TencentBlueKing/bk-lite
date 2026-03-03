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
    if (isLoading) return;
    getPermissionGroups();
  }, [isLoading]);

  const getPermissionGroups = async () => {
    setPageLoading(true);
    try {
      Promise.all([getAllUsers(), getUnitList()])
        .then(([usersResponse = [], unitsResponse = []]) => {
          setUserList(usersResponse);
          setUnitList(unitsResponse);
          const groupedByCategory = unitsResponse.reduce(
            (acc: UnitListItem, item: UnitListItem) => {
              if (!acc[item.category]) {
                acc[item.category] = [];
              }
              acc[item.category].push({
                ...item,
                label: item.unit_name,
                value: item.unit_id,
                unit: item.display_unit,
              });
              return acc;
            },
            {}
          );
          const transformedUnitList = Object.entries(groupedByCategory).map(
            ([category, children]) => ({
              label: category,
              children,
            })
          );
          setGroupedUnitList(transformedUnitList as GroupedUnitList[]);
        })
        .catch(() => {
          setPageLoading(false);
        });
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
