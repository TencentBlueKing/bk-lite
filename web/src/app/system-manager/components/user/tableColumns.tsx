import React from 'react';
import { Button, Popconfirm, Dropdown, Menu, Tooltip } from 'antd';
import { ColumnsType } from 'antd/es/table';
import PermissionWrapper from '@/components/permission';
import Icon from '@/components/icon';
import { UserDataType } from '@/app/system-manager/types/user';
import { getRandomColor } from '@/app/system-manager/utils';

interface TableColumnsProps {
  t: (key: string) => string;
  appIconMap: Map<string, string>;
  onEditUser: (userId: string) => void;
  onOpenPasswordModal: (userId: string) => void;
  onDeleteUser: (userId: string) => void;
  convertToLocalizedTime: (isoString: string, format?: string) => string;
}

export const createUserTableColumns = ({
  t,
  appIconMap,
  onEditUser,
  onOpenPasswordModal,
  onDeleteUser,
  convertToLocalizedTime,
}: TableColumnsProps): ColumnsType<UserDataType> => {
  return [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      width: 230,
      fixed: 'left',
      render: (text: string) => {
        const color = getRandomColor();
        return (
          <div className="flex" style={{ height: '17px', lineHeight: '17px' }}>
            <span
              className="h-5 w-5 rounded-[10px] text-center mr-1"
              style={{ color: '#ffffff', backgroundColor: color }}
            >
              {text?.substring(0, 1)}
            </span>
            <span>{text}</span>
          </div>
        );
      },
    },
    {
      title: t('system.user.table.lastName'),
      dataIndex: 'name',
      width: 100,
    },
    {
      title: t('system.user.table.email'),
      dataIndex: 'email',
      width: 185,
    },
    {
      title: t('system.user.table.lastLogin'),
      dataIndex: 'last_login',
      width: 180,
      render: (text: string) => text ? convertToLocalizedTime(text) : '-'
    },
    {
      title: t('system.user.table.role'),
      dataIndex: 'roles',
      width: 200,
      render: (roles: string[]) => {
        const groupedRoles = (roles || []).reduce((acc: Record<string, string[]>, role: string) => {
          const parts = role.split('@@');
          if (parts.length >= 2) {
            const appName = parts.slice(0, -1).join('@@');
            const roleName = parts[parts.length - 1];
            if (!acc[appName]) acc[appName] = [];
            acc[appName].push(roleName);
          } else {
            if (!acc['default']) acc['default'] = [];
            acc['default'].push(role);
          }
          return acc;
        }, {});

        const appEntries = Object.entries(groupedRoles);
        const visibleApps = appEntries.slice(0, 2);
        const hiddenApps = appEntries.slice(2);

        return (
          <div className="flex flex-wrap gap-2">
            {visibleApps.map(([appName, roleNames]) => (
              <div key={appName} className="flex items-center gap-1 rounded-xl border px-2 py-1">
                {appIconMap.get(appName) && (
                  <Tooltip title={appName} placement="top">
                    <div>
                      <Icon type={appIconMap.get(appName) || appName} className="w-4 h-4" />
                    </div>
                  </Tooltip>
                )}
                <span className="text-xs text-[var(--color-text-3)]">{roleNames.join(', ')}</span>
              </div>
            ))}
            {hiddenApps.length > 0 && (
              <Dropdown
                overlay={
                  <Menu>
                    {hiddenApps.map(([appName, roleNames]) => (
                      <Menu.Item key={appName}>
                        <div className="flex items-center gap-1">
                          {appIconMap.get(appName) && (
                            <Tooltip title={appName} placement="top" zIndex={10000}>
                              <div>
                                <Icon type={appIconMap.get(appName) || appName} className="w-4 h-4" />
                              </div>
                            </Tooltip>
                          )}
                          <span>{roleNames.join(', ')}</span>
                        </div>
                      </Menu.Item>
                    ))}
                  </Menu>
                }
                trigger={["click"]}
              >
                <span className="cursor-pointer text-blue-500 ml-1">...</span>
              </Dropdown>
            )}
          </div>
        );
      },
    },
    {
      title: t('common.actions'),
      dataIndex: 'key',
      width: 160,
      fixed: 'right',
      render: (key: string) => (
        <>
          <PermissionWrapper requiredPermissions={['Edit User']}>
            <Button type="link" className="mr-[8px]" onClick={() => onEditUser(key)}>
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit User']}>
            <Button type="link" className="mr-[8px]" onClick={() => onOpenPasswordModal(key)}>
              {t('system.common.password')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete User']}>
            <Popconfirm
              title={t('common.delConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => onDeleteUser(key)}
            >
              <Button type="link">{t('common.delete')}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      ),
    },
  ];
};