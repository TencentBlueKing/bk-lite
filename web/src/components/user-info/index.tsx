import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Dropdown, Avatar, MenuProps, message, Checkbox, Tree, Input } from 'antd';
import type { DataNode } from 'antd/lib/tree';
import { usePathname, useRouter } from 'next/navigation';
import { useSession, signOut } from 'next-auth/react';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import VersionModal from './versionModal';
import ThemeSwitcher from '@/components/theme';
import { useUserInfoContext } from '@/context/userInfo';
import { clearAuthToken } from '@/utils/crossDomainAuth';
import Cookies from 'js-cookie';
import type { Group } from '@/types/index';
import UserInformation from './userInformation'

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
  const [userInfoVisible, setUserInfoVisible] = useState<boolean>(false);
  const [dropdownVisible, setDropdownVisible] = useState<boolean>(false);
  const [groupPanelVisible, setGroupPanelVisible] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [includeChildren, setIncludeChildren] = useState<boolean>(false);
  const [searchValue, setSearchValue] = useState<string>('');
  const [userExpandedKeys, setUserExpandedKeys] = useState<string[]>([]);

  const username = displayName || (session?.user as any)?.username || 'Test';

  // 初始化时从 cookie 读取 include_children 状态
  useEffect(() => {
    const savedValue = Cookies.get('include_children');
    if (savedValue === '1') {
      setIncludeChildren(true);
    }
  }, []);

  // 初始化时默认展开所有节点
  useEffect(() => {
    if (groupTree.length > 0 && userExpandedKeys.length === 0) {
      const collectAllKeys = (groups: Group[]): string[] => {
        const keys: string[] = [];
        const collect = (grps: Group[]) => {
          grps.forEach(g => {
            keys.push(g.id);
            if (g.subGroups) collect(g.subGroups);
          });
        };
        collect(groups);
        return keys;
      };
      setUserExpandedKeys(collectAllKeys(groupTree));
    }
  }, [groupTree]);

  // 组面板引用，用于检测点击外部关闭
  const groupPanelRef = useRef<HTMLDivElement>(null);
  const groupMenuItemRef = useRef<HTMLDivElement>(null);

  // 搜索时自动展开所有节点（仅在从无搜索变为有搜索时触发）
  const prevSearchValueRef = useRef<string>('');
  useEffect(() => {
    // 只在从无搜索变为有搜索时展开
    if (searchValue && !prevSearchValueRef.current && groupTree.length > 0) {
      const collectAllKeys = (groups: Group[]): string[] => {
        const keys: string[] = [];
        const collect = (grps: Group[]) => {
          grps.forEach(g => {
            keys.push(g.id);
            if (g.subGroups) collect(g.subGroups);
          });
        };
        collect(groups);
        return keys;
      };
      setUserExpandedKeys(collectAllKeys(groupTree));
    }
    prevSearchValueRef.current = searchValue;
  }, [searchValue]);

  // 刷新页面逻辑
  const refreshPage = useCallback(() => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length > 2) {
      router.push(`/${pathSegments.slice(0, 2).join('/')}`);
    } else {
      window.location.reload();
    }
  }, [pathname, router]);

  // 处理复选框变化
  const handleIncludeChildrenChange = useCallback((checked: boolean) => {
    setIncludeChildren(checked);
    Cookies.set('include_children', checked ? '1' : '0', { expires: 365 });
    refreshPage();
  }, [refreshPage]);

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
    setGroupPanelVisible(false);
    refreshPage();
  }, [groupTree, pathname, router, setSelectedGroup, refreshPage]);

  // 组选择面板内容
  const groupPanelContent = useMemo(() => {
    const filterGroups = (groups: Group[]): Group[] => {
      return groups
        .filter(group => isSuperUser || (session?.user as any)?.username === 'kayla' || group.name !== 'OpsPilotGuest')
        .map(group => ({
          ...group,
          subGroups: group.subGroups ? filterGroups(group.subGroups) : undefined,
        }));
    };

    const filteredGroupTree = filterGroups(groupTree);

    // 搜索过滤逻辑（不分大小写）
    const searchFilterGroups = (groups: Group[], searchText: string): Group[] => {
      if (!searchText) return groups;

      const lowerSearch = searchText.toLowerCase();
      const result: Group[] = [];

      for (const group of groups) {
        const matchesSearch = group.name.toLowerCase().includes(lowerSearch);
        const filteredSubGroups = group.subGroups ? searchFilterGroups(group.subGroups, searchText) : [];

        if (matchesSearch || filteredSubGroups.length > 0) {
          result.push({
            ...group,
            subGroups: filteredSubGroups.length > 0 ? filteredSubGroups : group.subGroups,
          });
        }
      }

      return result;
    };

    const searchFiltered = searchFilterGroups(filteredGroupTree, searchValue);
    const treeData = convertGroupsToTreeData(searchFiltered, selectedGroup?.id);

    return (
      <>
        <div className="py-2 px-3 border-b border-[var(--color-border-2)]">
          <Checkbox
            checked={includeChildren}
            onChange={(e) => handleIncludeChildrenChange(e.target.checked)}
          >
            <span className="text-sm">{t('common.includeSubgroups')}</span>
          </Checkbox>
        </div>
        <div className="px-3 pt-2 pb-3 border-b border-[var(--color-border-2)]">
          <Input
            placeholder={t('common.search')}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            allowClear
            size="small"
          />
        </div>
        <div
          className="w-full px-2 py-2"
          style={{ flex: 1, overflow: 'auto', maxHeight: '300px' }}
        >
          <Tree
            treeData={treeData}
            selectedKeys={selectedGroup ? [selectedGroup.id] : []}
            expandedKeys={userExpandedKeys}
            onExpand={(keys) => setUserExpandedKeys(keys as string[])}
            onSelect={handleChangeGroup}
            showLine
            blockNode
          />
        </div>
      </>
    );
  }, [selectedGroup, groupTree, includeChildren, isSuperUser, session, searchValue, userExpandedKeys, handleChangeGroup, handleIncludeChildrenChange, t]);

  const dropdownItems: MenuProps['items'] = useMemo(() => {
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
          <div
            ref={groupMenuItemRef}
            className="w-full flex justify-between items-center"
            onClick={(e) => {
              e.stopPropagation();
              setGroupPanelVisible(!groupPanelVisible);
            }}
          >
            <span>{t('common.group')}</span>
            <span className="flex items-center gap-1 text-xs text-[var(--color-text-4)]">
              {selectedGroup?.name}
              <RightOutlined className="text-[10px]" />
            </span>
          </div>
        ),
      },
      { type: 'divider' },
      {
        key: 'userInfo',
        label: t('common.userInfo')
      },
      { type: 'divider' },
      {
        key: 'logout',
        label: t('common.logout'),
        disabled: isLoading,
      },
    ];

    return items;
  }, [selectedGroup, groupTree, isLoading, isSuperUser, session, groupPanelContent, groupPanelVisible, t]);

  const handleMenuClick = ({ key }: any) => {
    // 点击组选项时不关闭菜单（由 Popover 控制）
    if (key === 'groups') {
      return;
    }

    if (key === 'version') setVersionVisible(true);
    if (key === 'userInfo') setUserInfoVisible(true);
    if (key === 'logout') federatedLogout();

    setDropdownVisible(false);
    setGroupPanelVisible(false);
  };

  const handleOpenChange = (open: boolean) => {
    // 如果组面板打开着，保持下拉菜单打开
    if (groupPanelVisible && !open) {
      return;
    }
    setDropdownVisible(open);
  };

  return (
    <div className='flex items-center'>
      {username && (
        <Dropdown
          menu={{
            className: "min-w-[180px]",
            onClick: handleMenuClick,
            items: dropdownItems,
            subMenuOpenDelay: 0.1,
            subMenuCloseDelay: 0.1,
          }}
          trigger={['click']}
          open={dropdownVisible}
          onOpenChange={handleOpenChange}
        >
          <a className='cursor-pointer flex items-center gap-1.5' onClick={(e) => e.preventDefault()}>
            <Avatar size={20} style={{ backgroundColor: 'var(--color-primary)', fontSize: '12px' }}>
              {username.charAt(0).toUpperCase()}
            </Avatar>
            <span className="text-sm">{username}</span>
            <DownOutlined className="text-[10px]" />
          </a>
        </Dropdown>
      )}
      {/* 组选择面板 */}
      {groupPanelVisible && (
        <>
          {/* 透明遮罩层 - 点击关闭面板 */}
          <div
            className="fixed inset-0 z-[1059]"
            onClick={(e) => {
              e.stopPropagation();
              setGroupPanelVisible(false);
              setDropdownVisible(false);
            }}
          />
          {/* 面板内容 */}
          <div
            ref={groupPanelRef}
            className="fixed bg-[var(--color-bg-1)] border border-[var(--color-border-1)] rounded-lg shadow-lg z-[1060]"
            style={{
              top: '50px',
              right: '200px',
              width: '300px',
              maxHeight: '450px',
              display: 'flex',
              flexDirection: 'column'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {groupPanelContent}
          </div>
        </>
      )}
      <VersionModal visible={versionVisible} onClose={() => setVersionVisible(false)} />
      <UserInformation visible={userInfoVisible} onClose={() => setUserInfoVisible(false)} />
    </div>
  );
};

export default UserInfo;
