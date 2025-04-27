'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import { UserItem, Organization } from '@/app/cmdb/types/assetManage';
import { convertArray, filterNodesWithAllParents } from '@/app/cmdb/utils/common';
import Spin from '@/components/spin';
import { usePathname } from 'next/navigation';
import { useAliveController } from 'react-activation';
interface CommonContextType {
  permissionGroupsInfo: PermissionGroupsInfo;
  userList: UserItem[];
  authOrganizations: Organization[];
  organizations: Organization[];
}

interface PermissionGroupsInfo {
  is_all: boolean;
  group_ids: string[];
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [permissionGroupsInfo, setPermissionGroupsInfo] =
    useState<PermissionGroupsInfo>({
      is_all: true,
      group_ids: [],
    });
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [authOrganizations, setAuthOrganizations] = useState<Organization[]>(
    []
  );
  const [pageLoading, setPageLoading] = useState(false);
  const { get } = useApiClient();
  const { drop } = useAliveController();
  const pathname = usePathname();

  useEffect(() => {
    getPermissionGroups();
  }, []);

  useEffect(() => {
    if(drop && !pathname.startsWith('/cmdb/assetData')) {
      drop('assetData');
    }
  }, [pathname]);
    

  const getPermissionGroups = async () => {
    setPageLoading(true);
    try {
      const getUserList = get('/core/api/user_group/user_list/');
      const getOrganizationList = get('/core/api/user_group/group_list/');
      const getAuthOrganization = get('/core/api/user_group/user_groups/');
      Promise.all([getUserList, getOrganizationList, getAuthOrganization])
        .then((res) => {
          const userData: UserItem[] = res[0].users;
          const allOrganizations = res[1];
          const authOrganizationData: PermissionGroupsInfo = res[2];
          const groupIds = authOrganizationData.group_ids || [];
          const isAdmin = !!authOrganizationData.is_all || false;
          const authOrganizations = filterNodesWithAllParents(
            allOrganizations,
            groupIds
          );
          const authList: Organization[] = convertArray(
            isAdmin ? allOrganizations : authOrganizations
          );
          setPermissionGroupsInfo(authOrganizationData);
          setUserList(userData);
          setAuthOrganizations(authList);
          setOrganizations(convertArray(allOrganizations));
        })
        .finally(() => {
          setPageLoading(false);
        });
    } catch {
      setPageLoading(false);
    }
  };
  return pageLoading ? <Spin></Spin> : (
    <CommonContext.Provider
      value={{
        permissionGroupsInfo,
        userList,
        authOrganizations,
        organizations
      }}
    >
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => useContext(CommonContext);

export default CommonContextProvider;
