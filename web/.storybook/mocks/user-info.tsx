'use client';

import React, { createContext, useContext, useMemo, useState } from 'react';
import type { Group, UserInfoContextType } from '@/types';

const groupTree: Group[] = [
  {
    id: '1',
    name: 'Default',
    path: '/Default',
    hasAuth: true,
    subGroups: [
      {
        id: '11',
        name: 'Backend Team',
        path: '/Default/Backend Team',
        hasAuth: true,
        subGroups: [],
      },
      {
        id: '12',
        name: 'Frontend Team',
        path: '/Default/Frontend Team',
        hasAuth: true,
        subGroups: [],
      },
    ],
  },
  {
    id: '2',
    name: 'Shared Services',
    path: '/Shared Services',
    hasAuth: true,
    subGroups: [
      {
        id: '21',
        name: 'Platform',
        path: '/Shared Services/Platform',
        hasAuth: true,
        subGroups: [],
      },
    ],
  },
];

const flattenGroups = (groups: Group[]): Group[] =>
  groups.flatMap((group) => [
    group,
    ...(group.subGroups ? flattenGroups(group.subGroups) : []),
  ]);

const flatGroups = flattenGroups(groupTree);

const UserInfoContext = createContext<UserInfoContextType | undefined>(undefined);

export const UserInfoProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(groupTree[0]);

  const value = useMemo<UserInfoContextType>(
    () => ({
      loading: false,
      roles: ['admin'],
      groups: flatGroups,
      groupTree,
      selectedGroup,
      flatGroups,
      isSuperUser: true,
      isFirstLogin: false,
      userId: 'storybook-user',
      username: 'storybook',
      displayName: 'Storybook User',
      setSelectedGroup,
      refreshUserInfo: async () => {},
    }),
    [selectedGroup],
  );

  return (
    <UserInfoContext.Provider value={value}>
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
