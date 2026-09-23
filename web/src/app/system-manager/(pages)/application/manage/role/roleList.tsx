import React from 'react';
import { Skeleton, Popconfirm } from 'antd';
import Icon from '@/components/icon';
import PermissionWrapper from "@/components/permission";
import { Role } from '@/app/system-manager/types/application';

type TranslateFunction = (key: string) => string;

interface RoleListProps {
  loadingRoles: boolean;
  roleList: Role[];
  selectedRole: Role | null;
  onSelectRole: (role: Role) => void;
  showRoleModal: (role: Role | null) => void;
  onDeleteRole: (role: Role) => void;
  t: TranslateFunction;
}

const RoleList: React.FC<RoleListProps> = ({
  loadingRoles,
  roleList,
  selectedRole,
  onSelectRole,
  showRoleModal,
  onDeleteRole,
  t
}) => {

  const renderRoleItem = (role: Role) => (
    <div
      key={role.id}
      className={`flex items-center rounded-md justify-between p-2 mb-2 hover:bg-[var(--color-fill-1)] group ${selectedRole?.id === role.id ? 'bg-[var(--color-fill-2)] text-[var(--color-primary)]' : ''}`}
    >
      <div className="cursor-pointer text-sm" onClick={() => onSelectRole(role)}>
        {role.name}
      </div>
      <div className="flex text-base items-center text-[var(--color-text-3)]">
        <PermissionWrapper requiredPermissions={['Edit']} className="inline-block">
          <span className="hidden group-hover:inline cursor-pointer hover:text-[var(--color-text-active)]" onClick={() => showRoleModal(role)}>
            <Icon type="bianji" />
          </span>
        </PermissionWrapper>
        <PermissionWrapper requiredPermissions={['Delete']} className="inline-block ml-[5px]">
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => onDeleteRole(role)}
          >
            <span className="hidden group-hover:inline cursor-pointer hover:text-[var(--color-text-active)]">
              <Icon type="shanchu" />
            </span>
          </Popconfirm>
        </PermissionWrapper>
      </div>
    </div>
  );

  return (
    <div className="flex h-full min-h-0 w-[200px] shrink-0 flex-col overflow-hidden border-r border-[var(--color-border-1)] p-4">
      <div className="flex shrink-0 items-center justify-between">
        <h2 className="font-semibold">{t('system.role.title')}</h2>
        <PermissionWrapper requiredPermissions={['Add']}>
          <button
            type="button"
            aria-label={t('common.new')}
            className="grid h-7 w-7 place-items-center rounded-md text-[var(--color-text-3)] hover:bg-[var(--color-fill-1)] hover:text-[var(--color-primary)]"
            onClick={() => showRoleModal(null)}
          >
            <Icon type="xinzeng" className="text-xl" aria-hidden="true" />
          </button>
        </PermissionWrapper>
      </div>
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
        {loadingRoles ? (
          <Skeleton active paragraph={{ rows: 5 }} />
        ) : (
          roleList.map(renderRoleItem)
        )}
      </div>
    </div>
  );
};

export default RoleList;
