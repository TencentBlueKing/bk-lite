import React from 'react';
import { Skeleton, Popconfirm } from 'antd';
import Icon from '@/components/icon';
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
      key={role.role_id}
      className={`flex items-center rounded-md justify-between p-2 mb-2 hover:bg-[var(--color-fill-1)] group ${selectedRole?.role_id === role.role_id ? 'bg-[var(--color-fill-2)] text-[var(--color-primary)]' : ''}`}
    >
      <div className="cursor-pointer text-sm" onClick={() => onSelectRole(role)}>
        {role.display_name || role.role_name}
      </div>
      <div className="flex text-base items-center text-[var(--color-text-3)]">
        <span className="hidden group-hover:inline cursor-pointer hover:text-[var(--color-text-active)]" onClick={() => showRoleModal(role)}>
          <Icon type="bianji" />
        </span>
        <Popconfirm
          title={t('common.delConfirm')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          onConfirm={() => onDeleteRole(role)}
        >
          <span className="ml-[5px] hidden group-hover:inline cursor-pointer hover:text-[var(--color-text-active)]">
            <Icon type="shanchu" />
          </span>
        </Popconfirm>
      </div>
    </div>
  );

  return (
    <div className="w-[180px] pr-4 mr-4 border-r border-[var(--color-border-1)]">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">{t('system.role.title')}</h2>
        <div onClick={() => showRoleModal(null)}>
          <Icon type="xinzeng" className="text-xl cursor-pointer" />
        </div>
      </div>
      <div className="mt-4">
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
