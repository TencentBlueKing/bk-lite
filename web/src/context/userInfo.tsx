import React, { createContext, useContext, useState, useEffect } from 'react';
import useApiClient from '@/utils/request';
import { Group, UserInfoContextType } from '@/types/index'
import { convertTreeDataToGroupOptions } from '@/utils/index'
import Cookies from 'js-cookie';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';

const UserInfoContext = createContext<UserInfoContextType | undefined>(undefined);

// Filter out groups with name "OpsPilotGuest" (recursive processing for tree structure)
const filterOpsPilotGuest = (groups: Group[]): Group[] => {
  return groups
    .filter(group => group.name !== 'OpsPilotGuest')
    .map(group => ({
      ...group,
      subGroups: group.subGroups ? filterOpsPilotGuest(group.subGroups) : undefined,
    }));
};

export const UserInfoProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { get } = useApiClient();
  const { data: session, status } = useSession();
  const { isCheckingAuth } = useAuth(); // 添加 auth context
  const [selectedGroup, setSelectedGroupState] = useState<Group | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [displayName, setDisplayName] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [roles, setRoles] = useState<string[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [flatGroups, setFlatGroups] = useState<Group[]>([]);
  const [groupTree, setGroupTree] = useState<Group[]>([]);
  const [isSuperUser, setIsSuperUser] = useState<boolean>(true);
  const [isFirstLogin, setIsFirstLogin] = useState<boolean>(true);

  useEffect(() => {
    console.log('Session:', session);
    console.log('Status:', status);
    console.log('IsCheckingAuth:', isCheckingAuth);
    
    // 如果还在检查认证状态，不要进行API调用
    if (isCheckingAuth) {
      return;
    }
    
    if (status === 'authenticated' && session && session.user?.id) {
      const fetchLoginInfo = async () => {
        setLoading(true);
        try {
          console.log('Fetching login info for user:', session.user?.id);
          const data = await get('/core/api/login_info/');
          if (!data) {
            console.error('Failed to fetch login info: No data received');
            setLoading(false);
            return;
          }
          
          const { group_list: groupList, group_tree: groupTreeData, roles, is_superuser, is_first_login, user_id, display_name, username } = data;
          setGroups(groupList || []);
          const shouldSkipFilter = username === 'kayla';
          setGroupTree(is_superuser || shouldSkipFilter ? groupTreeData : filterOpsPilotGuest(groupTreeData || []));
          setRoles(roles || []);
          setIsSuperUser(!!is_superuser);
          setIsFirstLogin(!!is_first_login);
          setUserId(user_id || '');
          setDisplayName(display_name || session.user?.username || 'User');

          if (groupList?.length) {
            const flattenedGroups = convertTreeDataToGroupOptions(groupList);
            setFlatGroups(flattenedGroups);

            const groupIdFromCookie = Cookies.get('current_team');
            const initialGroup = flattenedGroups.find((group: Group) => String(group.id) === String(groupIdFromCookie));
            
            if (initialGroup) {
              setSelectedGroupState(initialGroup);
            } else {
              const filteredGroups = is_superuser || shouldSkipFilter
                ? [...flattenedGroups] 
                : flattenedGroups.filter((group: Group) => group.name !== 'OpsPilotGuest');
              const defaultGroup = filteredGroups[0];
              setSelectedGroupState(defaultGroup);
              Cookies.set('current_team', defaultGroup.id);
            }
          }
        } catch (err) {
          console.error('Failed to fetch login_info:', err);
        } finally {
          setLoading(false);
        }
      };

      fetchLoginInfo();
    }
  }, [status, isCheckingAuth]); // 添加 isCheckingAuth 到依赖

  const setSelectedGroup = (group: Group) => {
    setSelectedGroupState(group);
    Cookies.set('current_team', group.id);
  };

  return (
    <UserInfoContext.Provider value={{ loading, roles, groups, groupTree, selectedGroup, flatGroups, isSuperUser, isFirstLogin, userId, displayName, setSelectedGroup }}>
      {children}
    </UserInfoContext.Provider>
  );
};

export const useUserInfoContext = () => {
  const context = useContext(UserInfoContext);
  if (!context) {
    throw new Error('useUserInfoContext must be used within a UserInfoProvider');
  }
  return context;
};
