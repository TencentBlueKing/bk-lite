'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import { UserItem, Organization } from '@/app/log/types';
import { useUserInfoContext } from '@/context/userInfo';
import { transformTreeData } from '@/app/log/utils/common';
import useLogApi from '@/app/log/api';

interface CommonContextType {
  userList: UserItem[];
  authOrganizations: Organization[];
  /** 公共数据后台加载中；列表页等不依赖方无需等待 */
  commonLoading: boolean;
}

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [commonLoading, setCommonLoading] = useState(false);
  const { getAllUsers } = useLogApi();
  const { isLoading } = useApiClient();
  const commonContext = useUserInfoContext();

  useEffect(() => {
    if (isLoading) return;
    getPermissionGroups();
  }, [isLoading]);

  const getPermissionGroups = async () => {
    setCommonLoading(true);
    try {
      const responseData = await getAllUsers();
      const userData: UserItem[] = responseData || [];
      setUserList(userData);
    } finally {
      setCommonLoading(false);
    }
  };

  // 不再用全屏 Spin 挡住子路由：页面可先渲染，公共用户列表后台补齐
  return (
    <CommonContext.Provider
      value={{
        userList,
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
