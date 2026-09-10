import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import useApiClient from '@/utils/request';
import { Group, UserInfoContextType } from '@/types/index'
import { convertTreeDataToGroupOptions } from '@/utils/index'
import Cookies from 'js-cookie';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import {
  clearUserTeamPreference,
  CURRENT_TEAM_COOKIE,
  CURRENT_TEAM_OWNER_COOKIE,
  persistUserTeamPreference,
  resolveInitialGroup,
} from '@/utils/userTeamPreference';

export const UserInfoContext = createContext<UserInfoContextType | undefined>(undefined);

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
  const sessionUser = session?.user as any;
  const sessionUserIdentity = status === 'authenticated' && sessionUser?.id
    ? String(sessionUser.id)
    : '';
  const sessionUsername = sessionUser?.username;
  const [selectedGroup, setSelectedGroupState] = useState<Group | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [username, setUsername] = useState<string>('');
  const [displayName, setDisplayName] = useState<string>('');
  // login_info 返回前保持 loading，且不把用户当成首次登录。
  // 若 isFirstLogin 默认 true、loading 默认 false，控制台首页会在 useEffect
  // 拉完 /core/api/login_info/ 之前画出「初始化用户配置」弹窗。
  const [loading, setLoading] = useState<boolean>(true);
  const [roles, setRoles] = useState<string[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [flatGroups, setFlatGroups] = useState<Group[]>([]);
  const [groupTree, setGroupTree] = useState<Group[]>([]);
  const [isSuperUser, setIsSuperUser] = useState<boolean>(true);
  const [isFirstLogin, setIsFirstLogin] = useState<boolean>(false);
  const [loadedSessionIdentity, setLoadedSessionIdentity] = useState<string>('');
  const requestVersionRef = useRef(0);
  const activeSessionIdentityRef = useRef(sessionUserIdentity);
  activeSessionIdentityRef.current = sessionUserIdentity;

  const fetchLoginInfo = useCallback(async (expectedSessionIdentity: string) => {
    const requestVersion = ++requestVersionRef.current;
    setLoading(true);
    try {
      const data = await get('/core/api/login_info/');
      if (
        requestVersion !== requestVersionRef.current
        || activeSessionIdentityRef.current !== expectedSessionIdentity
      ) {
        return;
      }
      if (!data) {
        console.error('Failed to fetch login info: No data received');
        return;
      }

      const { group_list: groupList, group_tree: groupTreeData, roles, is_superuser, is_first_login, user_id, display_name, username } = data;
      const currentUserId = String(user_id || expectedSessionIdentity);
      setGroups(groupList || []);
      const shouldSkipFilter = username === 'kayla';
      setGroupTree(is_superuser || shouldSkipFilter ? (groupTreeData || []) : filterOpsPilotGuest(groupTreeData || []));
      setRoles(roles || []);
      setIsSuperUser(!!is_superuser);
      setIsFirstLogin(!!is_first_login);
      setUserId(currentUserId);
      setUsername(username || sessionUsername || 'admin');
      setDisplayName(display_name || sessionUsername || 'User');

      if (groupList?.length) {
        const flattenedGroups = convertTreeDataToGroupOptions(groupList);
        setFlatGroups(flattenedGroups);

        const filteredGroups = is_superuser || shouldSkipFilter
          ? [...flattenedGroups]
          : flattenedGroups.filter((group: Group) => group.name !== 'OpsPilotGuest');
        const initialGroup = resolveInitialGroup({
          groups: flattenedGroups,
          defaultGroup: filteredGroups[0],
          rememberedGroupId: Cookies.get(CURRENT_TEAM_COOKIE),
          rememberedOwnerId: Cookies.get(CURRENT_TEAM_OWNER_COOKIE),
          currentUserId,
        });

        if (initialGroup) {
          setSelectedGroupState(initialGroup);
          persistUserTeamPreference(initialGroup.id, currentUserId);
        } else {
          setSelectedGroupState(null);
          clearUserTeamPreference();
        }
      } else {
        setFlatGroups([]);
        setSelectedGroupState(null);
        clearUserTeamPreference();
      }
    } catch (err) {
      console.error('Failed to fetch login_info:', err);
    } finally {
      if (
        requestVersion === requestVersionRef.current
        && activeSessionIdentityRef.current === expectedSessionIdentity
      ) {
        setLoadedSessionIdentity(expectedSessionIdentity);
        setLoading(false);
      }
    }
  }, [get, sessionUsername]);

  useEffect(() => {
    // 如果还在检查认证状态，不要进行API调用
    if (isCheckingAuth) {
      return;
    }

    if (status === 'authenticated' && sessionUserIdentity) {
      setSelectedGroupState(null);
      setGroups([]);
      setFlatGroups([]);
      setGroupTree([]);
      setRoles([]);
      setUserId('');
      setUsername('');
      setDisplayName('');
      setLoadedSessionIdentity('');
      void fetchLoginInfo(sessionUserIdentity);
      return;
    }

    requestVersionRef.current += 1;
    setSelectedGroupState(null);
    setLoadedSessionIdentity('');
    setLoading(status === 'loading');
  }, [fetchLoginInfo, isCheckingAuth, sessionUserIdentity, status]);

  const setSelectedGroup = (group: Group) => {
    setSelectedGroupState(group);
    persistUserTeamPreference(group.id, userId || sessionUserIdentity);
  };

  const refreshUserInfo = async () => {
    if (sessionUserIdentity) {
      await fetchLoginInfo(sessionUserIdentity);
    }
  };

  const hasCurrentSessionData = Boolean(
    sessionUserIdentity && loadedSessionIdentity === sessionUserIdentity,
  );
  const isSessionIdentityChanging = Boolean(
    status === 'authenticated' && sessionUserIdentity && !hasCurrentSessionData,
  );

  return (
    <UserInfoContext.Provider value={{ loading: loading || isSessionIdentityChanging, roles, groups, groupTree, selectedGroup: hasCurrentSessionData ? selectedGroup : null, flatGroups, isSuperUser, isFirstLogin, userId, username, displayName, setSelectedGroup, refreshUserInfo }}>
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
