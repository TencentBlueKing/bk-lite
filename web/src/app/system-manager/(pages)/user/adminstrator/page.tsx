"use client";

import React, { useMemo } from 'react';
import { Button, Popconfirm, Space, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getRandomColor } from '@/app/system-manager/utils';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import SystemManagerWorkbenchShell, {
  SystemManagerWorkbenchPanel,
} from '@/app/system-manager/components/system-manager-workbench-shell';
import {
  useAdminUsersList,
  useAdminActions,
  useAddAdminModal,
} from '@/app/system-manager/hooks/useAdminUsers';

const AdminUsers: React.FC = () => {
  const { t } = useTranslation();

  const {
    loading,
    adminUsers,
    currentPage,
    pageSize,
    total,
    fetchAdminUsers,
    handleTableChange,
  } = useAdminUsersList(t);

  const { handleRevokeAdmin } = useAdminActions(t, fetchAdminUsers);

  const {
    addAdminModalOpen,
    selectedUsers,
    addAdminLoading,
    modalLoading,
    normalUsers,
    setSelectedUsers,
    openAddAdminModal,
    closeAddAdminModal,
    handleAddAdmin,
  } = useAddAdminModal(adminUsers, t, fetchAdminUsers);

  const columns = useMemo(
    () => [
      {
        title: t('system.user.table.username'),
        dataIndex: 'username',
        width: 230,
        render: (text: string) => {
          const color = getRandomColor();
          return (
            <div className="flex h-[17px] items-center leading-[17px]">
              <span
                className="mr-1 flex h-5 w-5 items-center justify-center rounded-[10px] text-center text-[var(--color-bg)]"
                style={{ backgroundColor: color }}
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
        dataIndex: 'display_name',
        width: 200,
      },
      {
        title: t('common.actions'),
        dataIndex: 'id',
        width: 120,
        render: (id: string) => (
          <Space>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Popconfirm
                title={t('system.administrator.revokeConfirm')}
                description={t('system.administrator.revokeConfirmContent')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => handleRevokeAdmin(id)}
              >
                <Button type="link" size="small" danger>
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            </PermissionWrapper>
          </Space>
        ),
      },
    ],
    [t, handleRevokeAdmin]
  );

  return (
    <>
      <SystemManagerWorkbenchShell
        header={(
          <TopSection
            title={t('system.administrator.title')}
            content={t('system.administrator.desc')}
          />
        )}
        right={(
          <SystemManagerWorkbenchPanel bodyClassName="flex min-h-0 flex-col p-4">
            <div className="mb-4 flex justify-end">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={openAddAdminModal}
                >
                  {t('common.new')}
                </Button>
              </PermissionWrapper>
            </div>
            <SystemManagerFillTable>
              <CustomTable
                loading={loading}
                columns={columns}
                dataSource={adminUsers}
                pagination={{
                  current: currentPage,
                  pageSize,
                  total,
                  showSizeChanger: true,
                  showQuickJumper: true,
                  showTotal: (total: number, range: [number, number]) =>
                    `${range[0]}-${range[1]} / ${total}`,
                  onChange: (page: number, size?: number) => {
                    if (page !== currentPage || (size && size !== pageSize)) {
                      handleTableChange(page, size);
                    }
                  },
                }}
              />
            </SystemManagerFillTable>
          </SystemManagerWorkbenchPanel>
        )}
      />

      <OperateModal
        title={t('system.administrator.addAdmin')}
        open={addAdminModalOpen}
        onOk={handleAddAdmin}
        onCancel={closeAddAdminModal}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        destroyOnHidden={true}
      >
        <div className="mb-4">
          <label className="mb-2 block text-sm font-medium text-[var(--color-text-1)]">
            {t('system.administrator.selectUsers')}
          </label>
          <Select
            showSearch
            mode="multiple"
            allowClear
            className="w-full"
            disabled={addAdminLoading}
            loading={addAdminLoading}
            placeholder={t('system.administrator.selectUsersPlaceholder')}
            value={selectedUsers}
            onChange={setSelectedUsers}
            filterOption={(input, option) =>
              typeof option?.label === 'string' && option.label.toLowerCase().includes(input.toLowerCase())
            }
          >
            {normalUsers.map(user => (
              <Select.Option key={user.id} value={user.id} label={`${user.display_name}(${user.username})`}>
                {user.display_name}({user.username})
              </Select.Option>
            ))}
          </Select>
        </div>
        <div className="text-sm text-[var(--color-text-3)]">
          {t('system.administrator.addAdminTip')}
        </div>
      </OperateModal>
    </>
  );
};

export default AdminUsers;
