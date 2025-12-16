"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Button, message, Modal, Popconfirm, Space, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useRoleApi } from '@/app/system-manager/api/application';
import { getRandomColor } from '@/app/system-manager/utils';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';

interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string;
  is_superuser: boolean;
  last_login?: string;
  created_at?: string;
}

const AdminUsers: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(false);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [total, setTotal] = useState<number>(0);
  const [normalUsers, setNormalUsers] = useState<AdminUser[]>([]);
  const [addAdminModalOpen, setAddAdminModalOpen] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [addAdminLoading, setAddAdminLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);

  const { t } = useTranslation();
  const { confirm } = Modal;
  const { getUsersList } = useUserApi();
  const { getAllUser, addUser, deleteUser } = useRoleApi();
  
  const isInitializedRef = useRef(false);
  const fetchingRef = useRef(false);

  const fetchAdminUsers = useCallback(async (params: any = {}) => {
    if (fetchingRef.current) {
      return;
    }
    
    fetchingRef.current = true;
    setLoading(true);
    try {
      const res = await getUsersList({
        is_superuser: 1,
        page: params.page || currentPage,
        page_size: params.page_size || pageSize,
        ...params,
      });
      
      const data = res.users.map((item: any) => ({
        key: item.id,
        id: item.id,
        username: item.username,
        display_name: item.display_name,
        email: item.email,
        is_superuser: item.is_superuser,
        last_login: item.last_login,
        created_at: item.created_at,
      }));
      
      setAdminUsers(data);
      setTotal(res.count);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [currentPage, pageSize]);

  const fetchAllUsers = async () => {
    setAddAdminLoading(true);
    try {
      const allUsers = await getAllUser();
      
      const adminUserIds = new Set(adminUsers.map(admin => admin.id));
      const availableUsers = allUsers.filter((item: any) => 
        !item.is_superuser && !adminUserIds.has(item.id)
      ).map((item: any) => ({
        key: item.id,
        id: item.id,
        username: item.username,
        display_name: item.display_name,
        email: item.email,
        is_superuser: item.is_superuser,
        last_login: item.last_login,
        created_at: item.created_at,
      }));
      
      setNormalUsers(availableUsers);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
      message.error(t('common.fetchFailed'));
    } finally {
      setAddAdminLoading(false);
    }
  };

  const handleRevokeAdmin = async (userId: string) => {
    confirm({
      title: t('system.administrator.revokeConfirm'),
      content: t('system.administrator.revokeConfirmContent'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        try {
          await deleteUser({ 
            user_ids: [userId],
            is_superuser: true
          });
          message.success(t('system.administrator.revokeSuccess'));
          fetchAdminUsers();
        } catch {
          message.error(t('system.administrator.revokeFailed'));
        }
      },
    });
  };

  const handleAddAdmin = async () => {
    if (selectedUsers.length === 0) {
      message.warning(t('system.administrator.pleaseSelectUser'));
      return;
    }

    setModalLoading(true);
    try {
      await addUser({ 
        user_ids: selectedUsers, 
        is_superuser: true 
      });
      message.success(t('system.administrator.addSuccess'));
      setAddAdminModalOpen(false);
      setSelectedUsers([]);
      fetchAdminUsers();
    } catch (error) {
      console.error('Failed to add admin:', error);
      message.error(t('system.administrator.addFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleTableChange = (page: number, newPageSize?: number) => {
    const finalPageSize = newPageSize || pageSize;
    setCurrentPage(page);
    if (newPageSize && newPageSize !== pageSize) {
      setPageSize(newPageSize);
    }
    fetchAdminUsers({ page, page_size: finalPageSize });
  };

  const openAddAdminModal = () => {
    if (!normalUsers.length) fetchAllUsers();
    setAddAdminModalOpen(true);
  };

  const closeAddAdminModal = () => {
    setAddAdminModalOpen(false);
    setSelectedUsers([]);
  };

  useEffect(() => {
    if (isInitializedRef.current) {
      return;
    }
    isInitializedRef.current = true;
    fetchAdminUsers();
  }, []);

  const columns = [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      width: 230,
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
  ];

  return (
    <>
      <PageLayout
        height='calc(100vh - 240px)'
        topSection={
          <TopSection 
            title={t('system.administrator.title')} 
            content={t('system.administrator.desc')} 
          />
        }
        rightSection={
          <div>
            <div className="w-full mb-4 flex justify-end">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={openAddAdminModal}
                >
                  {t('system.administrator.addAdmin')}
                </Button>
              </PermissionWrapper>
            </div>
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
              scroll={{ y: 'calc(100vh - 430px)' }}
            />
          </div>
        }
      />

      {/* 添加管理员弹窗 */}
      <OperateModal
        title={t('system.administrator.addAdmin')}
        open={addAdminModalOpen}
        onOk={handleAddAdmin}
        onCancel={closeAddAdminModal}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        destroyOnClose={true}
      >
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {t('system.administrator.selectUsers')}
          </label>
          <Select
            showSearch
            mode="multiple"
            allowClear
            disabled={addAdminLoading}
            loading={addAdminLoading}
            style={{ width: '100%' }}
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
        <div className="text-sm text-gray-500">
          {t('system.administrator.addAdminTip')}
        </div>
      </OperateModal>
    </>
  );
};

export default AdminUsers;