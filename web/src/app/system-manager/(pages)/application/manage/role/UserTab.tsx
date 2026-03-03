import React, { useMemo } from 'react';
import { Button, Input, Spin, Popconfirm, Form, Select, Modal } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from "@/components/permission";
import type { User } from '@/app/system-manager/types/application';

const { Search } = Input;
const { Option } = Select;
const { confirm } = Modal;

interface UserTabProps {
  tableData: User[];
  loading: boolean;
  currentPage: number;
  pageSize: number;
  total: number;
  selectedUserKeys: React.Key[];
  setSelectedUserKeys: (keys: React.Key[]) => void;
  allUserList: User[];
  allUserLoading: boolean;
  deleteLoading: boolean;
  addUserModalOpen: boolean;
  setAddUserModalOpen: (open: boolean) => void;
  modalLoading: boolean;
  t: (key: string) => string;
  onSearch: (value: string) => void;
  onTableChange: (page: number, size?: number) => void;
  onAddUser: (userIds: number[]) => Promise<void>;
  onDeleteUser: (record: User) => Promise<void>;
  onBatchDelete: () => Promise<boolean>;
  onFetchAllUsers: () => Promise<void>;
}

const UserTab: React.FC<UserTabProps> = ({
  tableData,
  loading,
  currentPage,
  pageSize,
  total,
  selectedUserKeys,
  setSelectedUserKeys,
  allUserList,
  allUserLoading,
  deleteLoading,
  addUserModalOpen,
  setAddUserModalOpen,
  modalLoading,
  t,
  onSearch,
  onTableChange,
  onAddUser,
  onDeleteUser,
  onBatchDelete,
  onFetchAllUsers
}) => {
  const [addUserForm] = Form.useForm();

  const columns = useMemo(() => [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: t('system.user.table.lastName'),
      dataIndex: 'display_name',
      key: 'display_name',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, record: User) => (
        <PermissionWrapper requiredPermissions={['Remove user']}>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => onDeleteUser(record)}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </PermissionWrapper>
      ),
    },
  ], [t, onDeleteUser]);

  const openUserModal = () => {
    if (!allUserList.length) onFetchAllUsers();
    addUserForm.resetFields();
    setAddUserModalOpen(true);
  };

  const handleAddUser = async () => {
    try {
      const values = await addUserForm.validateFields();
      await onAddUser(values.users);
      setAddUserModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    }
  };

  const handleBatchDeleteClick = () => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        await onBatchDelete();
      },
    });
  };

  return (
    <>
      <div className="flex justify-end mb-4">
        <Search
          allowClear
          enterButton
          className='w-60 mr-[8px]'
          onSearch={onSearch}
          placeholder={`${t('common.search')}`}
        />
        <PermissionWrapper requiredPermissions={['Add user']}>
          <Button
            className="mr-[8px]"
            type="primary"
            onClick={openUserModal}
          >
            +{t('common.add')}
          </Button>
        </PermissionWrapper>
        <PermissionWrapper requiredPermissions={['Remove user']}>
          <Button
            loading={deleteLoading}
            onClick={handleBatchDeleteClick}
            disabled={selectedUserKeys.length === 0 || deleteLoading}
          >
            {t('system.common.modifydelete')}
          </Button>
        </PermissionWrapper>
      </div>
      <Spin spinning={loading}>
        <CustomTable
          scroll={{ y: 'calc(100vh - 435px)' }}
          rowSelection={{
            selectedRowKeys: selectedUserKeys,
            onChange: (selectedRowKeys) => setSelectedUserKeys(selectedRowKeys as React.Key[]),
          }}
          columns={columns}
          dataSource={tableData}
          rowKey={(record) => record.id}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: total,
            onChange: onTableChange,
          }}
        />
      </Spin>
      <OperateModal
        title={t('system.role.addUser')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={addUserModalOpen}
        onOk={handleAddUser}
        onCancel={() => setAddUserModalOpen(false)}
      >
        <Form form={addUserForm}>
          <Form.Item
            name="users"
            label={t('system.role.users')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Select
              showSearch
              mode="multiple"
              disabled={allUserLoading}
              loading={allUserLoading}
              placeholder={`${t('common.select')}${t('system.role.users')}`}
              filterOption={(input, option) =>
                typeof option?.label === 'string' && option.label.toLowerCase().includes(input.toLowerCase())
              }
            >
              {allUserList.map(user => (
                <Option key={user.id} value={user.id} label={`${user.display_name}(${user.username})`}>
                  {user.display_name}({user.username})
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default UserTab;
