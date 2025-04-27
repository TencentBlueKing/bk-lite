import React, { useState, useCallback, useMemo } from 'react';
import { Dropdown, Space, Avatar, Menu, MenuProps, message } from 'antd';
import { usePathname, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import VersionModal from './versionModal';
import ThemeSwitcher from '@/components/theme';
import { useUserInfoContext } from '@/context/userInfo';

interface GroupItemProps {
  id: string;
  name: string;
  isSelected: boolean;
  onClick: (id: string) => void;
}

const GroupItem: React.FC<GroupItemProps> = ({ id, name, isSelected, onClick }) => (
  <Space onClick={() => onClick(id)}>
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        isSelected ? 'bg-[var(--color-success)]' : 'bg-[var(--color-fill-4)]'
      }`}
    />
    <span className="text-sm">{name}</span>
  </Space>
);

const UserInfo: React.FC = () => {
  const { data: session } = useSession();
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const { flatGroups, selectedGroup, setSelectedGroup } = useUserInfoContext();

  const [versionVisible, setVersionVisible] = useState<boolean>(false);
  const [dropdownVisible, setDropdownVisible] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const isConsole = process.env.NEXT_PUBLIC_IS_OPS_CONSOLE === 'true';
  const username = session?.username || 'Test';

  const federatedLogout = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/auth/federated-logout', {
        method: 'POST',
      });

      const data = await response.json();
      if (response.ok) {
        window.location.href = data.url;
      } else {
        throw new Error(data.error || 'Failed to log out');
      }
    } catch (error) {
      console.error('Logout error:', error);
      message.error(t('common.logoutFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  const handleChangeGroup = useCallback((key: string) => {
    const nextGroup = flatGroups.find(group => group.id === key);
    if (!nextGroup) return;

    setSelectedGroup(nextGroup);
    setDropdownVisible(false);

    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length > 2) {
      router.push(`/${pathSegments.slice(0, 2).join('/')}`);
    } else {
      window.location.reload();
    }
  }, [flatGroups, pathname, router, setSelectedGroup]);

  const dropdownItems: MenuProps['items'] = useMemo(() => {
    const items: MenuProps['items'] = [
      {
        key: 'themeSwitch',
        label: <ThemeSwitcher />,
      },
    ];

    if (!isConsole) {
      items.push(
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
          children: flatGroups.map((group) => ({
            key: group.id,
            label: (
              <GroupItem
                id={group.id}
                name={group.name}
                isSelected={selectedGroup?.name === group.name}
                onClick={handleChangeGroup}
              />
            ),
          })),
        },
        { type: 'divider' }
      );
    }

    items.push({
      key: 'logout',
      label: t('common.logout'),
      disabled: isLoading,
    });

    return items;
  }, [t, selectedGroup, flatGroups, handleChangeGroup, isLoading, isConsole]);

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
