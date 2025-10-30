import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Dropdown, Space, Avatar, Menu, MenuProps, message, Checkbox, Tree } from 'antd';
import type { DataNode } from 'antd/lib/tree';
import { usePathname, useRouter } from 'next/navigation';
import { useSession, signOut } from 'next-auth/react';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import VersionModal from './versionModal';
import ThemeSwitcher from '@/components/theme';
import { useUserInfoContext } from '@/context/userInfo';
import { clearAuthToken } from '@/utils/crossDomainAuth';
import Cookies from 'js-cookie';
import type { Group } from '@/types/index';

// 将 Group 转换为 Tree DataNode
const convertGroupsToTreeData = (groups: Group[], selectedGroupId: string | undefined): DataNode[] => {
  return groups.map(group => ({
    key: group.id,
    title: group.name,
    selectable: true,
    children: group.subGroups && group.subGroups.length > 0
      ? convertGroupsToTreeData(group.subGroups, selectedGroupId)
      : undefined,
  }));
};

const UserInfo: React.FC = () => {
  const { data: session } = useSession();
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const { groupTree, selectedGroup, setSelectedGroup, displayName, isSuperUser } = useUserInfoContext();

  const [versionVisible, setVersionVisible] = useState<boolean>(false);
  const [dropdownVisible, setDropdownVisible] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [includeChildren, setIncludeChildren] = useState<boolean>(false);

  const username = displayName || session?.user?.username || 'Test';

  // 初始化时从 cookie 读取 include_children 状态
  useEffect(() => {
    const savedValue = Cookies.get('include_children');
    if (savedValue === '1') {
      setIncludeChildren(true);
    }
  }, []);

  // 处理复选框变化
  const handleIncludeChildrenChange = useCallback((checked: boolean) => {
    setIncludeChildren(checked);
    Cookies.set('include_children', checked ? '1' : '0', { expires: 365 });
  }, []);

  const federatedLogout = useCallback(async () => {
    setIsLoading(true);
    try {
      // Call logout API for server-side cleanup
      await fetch('/api/auth/federated-logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      // Clear authentication token
      clearAuthToken();

      // Use NextAuth's signOut to clear client session
      await signOut({ redirect: false });

      // Build login page URL with current page as callback URL after successful login
      const currentPageUrl = `${window.location.origin}${pathname}`;
      const loginUrl = `/auth/signin?callbackUrl=${encodeURIComponent(currentPageUrl)}`;

      // Redirect to login page
      window.location.href = loginUrl;
    } catch (error) {
      console.error('Logout error:', error);
      message.error(t('common.logoutFailed'));

      // Even if API call fails, still clear token and redirect to login page
      clearAuthToken();
      await signOut({ redirect: false });

      const currentPageUrl = `${window.location.origin}${pathname}`;
      const loginUrl = `/auth/signin?callbackUrl=${encodeURIComponent(currentPageUrl)}`;
      window.location.href = loginUrl;
    } finally {
      setIsLoading(false);
    }
  }, [pathname, t]);

  const handleChangeGroup = useCallback(async (selectedKeys: React.Key[]) => {
    if (selectedKeys.length === 0) return;

    const selectedKey = selectedKeys[0] as string;

    const findGroup = (groups: Group[], id: string): Group | null => {
      for (const group of groups) {
        if (group.id === id) return group;
        if (group.subGroups) {
          const found = findGroup(group.subGroups, id);
          if (found) return found;
        }
      }
      return null;
    };

    const nextGroup = findGroup(groupTree, selectedKey);
    if (!nextGroup) return;

    setSelectedGroup(nextGroup);
    setDropdownVisible(false);

    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length > 2) {
      router.push(`/${pathSegments.slice(0, 2).join('/')}`);
    } else {
      window.location.reload();
    }
  }, [groupTree, pathname, router, setSelectedGroup]);

  const dropdownItems: MenuProps['items'] = useMemo(() => {
    const filterGroups = (groups: Group[]): Group[] => {
      return groups
        .filter(group => isSuperUser || session?.user?.username === 'kayla' || group.name !== 'OpsPilotGuest')
        .map(group => ({
          ...group,
          subGroups: group.subGroups ? filterGroups(group.subGroups) : undefined,
        }));
    };

    const filteredGroupTree = filterGroups(groupTree);
    const treeData = convertGroupsToTreeData(filteredGroupTree, selectedGroup?.id);

    const items: MenuProps['items'] = [
      {
        key: 'themeSwitch',
        label: <ThemeSwitcher />,
      },
      { type: 'divider' },
      {
        key: 'version',
        label: (
          <div className="w-full flex justify-between items-center">
            <span>{t('common.version')}</span>
            <span className="text-xs text-[var(--color-text-4)]">3.1.0</span>
          </div>
        ),
      },
      { type: 'divider' },
      {
        key: 'groups',
        label: (
          <div className="w-full flex justify-between items-center">
            <span>{t('common.group')}</span>
            <span className="text-xs text-[var(--color-text-4)]">{selectedGroup?.name}</span>
          </div>
        ),
        children: [
          {
            key: 'group-tree-container',
            label: (
              <div className="w-full" style={{ width: '180px' }}>
                <div
                  className="w-full py-2 px-3 border-b border-[var(--color-border-2)]"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Checkbox
                    checked={includeChildren}
                    onChange={(e) => {
                      e.stopPropagation();
                      handleIncludeChildrenChange(e.target.checked);
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="text-sm">{t('common.includeSubgroups')}</span>
                  </Checkbox>
                </div>
                <div
                  className="w-full py-2"
                  style={{ height: '900px', overflow: 'auto' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Tree
                    treeData={treeData}
                    selectedKeys={selectedGroup ? [selectedGroup.id] : []}
                    onSelect={handleChangeGroup}
                    defaultExpandAll
                    showLine
                    blockNode
                  />
                </div>
              </div>
            ),
            disabled: true,
            style: { cursor: 'default', padding: 0 },
          },
        ],
        popupClassName: 'user-groups-submenu'
      },
      { type: 'divider' },
      {
        key: 'logout',
        label: t('common.logout'),
        disabled: isLoading,
      },
    ];

    return items;
  }, [selectedGroup, groupTree, isLoading, includeChildren, isSuperUser, session]);

  const handleMenuClick = ({ key }: any) => {
    if (key === 'version') setVersionVisible(true);
    if (key === 'logout') federatedLogout();
    setDropdownVisible(false);
  };

  const userMenu = (
    <Menu
      className="min-w-[180px]"
      onClick={handleMenuClick}
      items={dropdownItems}
      subMenuOpenDelay={0.1}
      subMenuCloseDelay={0.1}
    />
  );

  return (
    <div className='flex items-center'>
      {username && (
        <Dropdown
          overlay={userMenu}
          trigger={['click']}
          visible={dropdownVisible}
          onVisibleChange={setDropdownVisible}
        >
          <a className='cursor-pointer' onClick={(e) => e.preventDefault()}>
            <Space className='text-sm'>
              <Avatar size={20} style={{ backgroundColor: 'var(--color-primary)', verticalAlign: 'middle' }}>
                {username.charAt(0).toUpperCase()}
              </Avatar>
              {username}
              <DownOutlined style={{ fontSize: '10px' }} />
            </Space>
          </a>
        </Dropdown>
      )}
      <VersionModal visible={versionVisible} onClose={() => setVersionVisible(false)} />
    </div>
  );
};

export default UserInfo;
