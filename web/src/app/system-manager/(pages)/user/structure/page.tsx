'use client';

import React, { useRef, useCallback, useMemo } from 'react';
import { Input, Button, Spin, Form, Dropdown, Menu } from 'antd';
import TopSection from '@/components/top-section';
import UserModal, { ModalRef } from './userModal';
import PasswordModal, { PasswordModalRef } from '@/app/system-manager/components/user/passwordModal';
import GroupEditModal, { GroupModalRef } from '@/app/system-manager/components/group/GroupEditModal';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import CustomTable from '@/components/custom-table';
import { TableRowSelection } from '@/app/system-manager/types/user';
import PageLayout from '@/components/page-layout';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import GroupTree from '@/app/system-manager/components/user/GroupTree';
import { createUserTableColumns } from '@/app/system-manager/components/user/tableColumns';
import { useTreeData, useUserTable, useGroupManagement } from '@/app/system-manager/hooks/useUserStructure';
import usePermissions from '@/hooks/usePermissions';
import { DownOutlined } from '@ant-design/icons';
import commonStyles from '@/app/system-manager/styles/common.module.scss';
import styles from './index.module.scss';

const { Search } = Input;
const normalizeUserId = (userId: React.Key) => String(userId);

const User: React.FC = () => {
  const { t } = useTranslation();
  const { clientData } = useClientData();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { hasPermission } = usePermissions();

  const userModalRef = useRef<ModalRef>(null);
  const passwordModalRef = useRef<PasswordModalRef>(null);
  const groupEditModalRef = useRef<GroupModalRef>(null);

  const {
    treeData,
    filteredTreeData,
    treeLoading,
    treeSearchValue,
    selectedTreeKeys,
    fetchTreeData,
    handleTreeSearchChange,
    handleTreeSelect,
    setSelectedTreeKeys,
  } = useTreeData(t);

  const {
    tableData,
    loading,
    total,
    currentPage,
    pageSize,
    searchValue,
    selectedRowKeys,
    fetchUsers,
    handleUserSearch,
    handleTableChange,
    handleDeleteUser,
    handleChangeUserStatus,
    handleBatchUserStatus,
    setSelectedRowKeys,
    setCurrentPage,
  } = useUserTable(t, selectedTreeKeys);

  const {
    addGroupModalOpen,
    addSubGroupModalOpen,
    addGroupLoading,
    addGroupFormRef,
    handleAddRootGroup,
    handleGroupAction,
    onAddGroup,
    closeGroupModals,
  } = useGroupManagement(
    t,
    treeData,
    selectedTreeKeys,
    searchValue,
    currentPage,
    pageSize,
    fetchTreeData,
    fetchUsers,
    setSelectedTreeKeys,
    setSelectedRowKeys,
    groupEditModalRef
  );

  const appIconMap = useMemo(() => new Map(
    clientData
      .filter(item => item.icon)
      .map((item) => [item.name, item.icon as string])
  ), [clientData]);

  const columns = useMemo(() => createUserTableColumns({
    t,
    appIconMap,
    convertToLocalizedTime,
    onEditUser: (userId: React.Key) => {
      userModalRef.current?.showModal({ type: 'edit', userId: normalizeUserId(userId) });
    },
    onOpenPasswordModal: (userId: React.Key) => {
      passwordModalRef.current?.showModal({ userId: normalizeUserId(userId) });
    },
    onDeleteUser: handleDeleteUser,
    onChangeUserStatus: handleChangeUserStatus,
  }), [t, appIconMap, convertToLocalizedTime, handleDeleteUser, handleChangeUserStatus]);

  const rowSelection: TableRowSelection<any> = useMemo(() => ({
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => setSelectedRowKeys(newSelectedRowKeys),
  }), [selectedRowKeys, setSelectedRowKeys]);

  const onTreeSelect = useCallback((selectedKeys: React.Key[]) => {
    setSelectedRowKeys([]);
    setCurrentPage(1);
    handleTreeSelect(selectedKeys, fetchUsers, searchValue, pageSize);
  }, [setSelectedRowKeys, setCurrentPage, handleTreeSelect, fetchUsers, searchValue, pageSize]);

  const openUserModal = useCallback((type: 'add') => {
    userModalRef.current?.showModal({
      type,
      groupKeys: type === 'add' ? selectedTreeKeys : [],
    });
  }, [selectedTreeKeys]);

  const onSuccessUserModal = useCallback(() => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  }, [fetchUsers, searchValue, currentPage, pageSize]);

  const onSuccessGroupEdit = useCallback(async () => {
    await fetchTreeData();
    if (selectedTreeKeys.length > 0) {
      fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
    }
  }, [fetchTreeData, selectedTreeKeys, fetchUsers, searchValue, currentPage, pageSize]);

  const isDeleteDisabled = selectedRowKeys.length === 0;
  const canEditUser = hasPermission(['Edit User']);
  const canDeleteUser = hasPermission(['Delete User']);
  const hasBatchActions = canEditUser || canDeleteUser;

  return (
    <>
      <PageLayout
        height='calc(100vh - 240px)'
        topSection={<TopSection title={t('system.user.title')} content={t('system.user.desc')} />}
        leftSection={
          <div className={`w-full h-full flex flex-col ${styles.userInfo}`}>
            <GroupTree
              treeData={filteredTreeData}
              searchValue={treeSearchValue}
              onSearchChange={handleTreeSearchChange}
              onAddRootGroup={handleAddRootGroup}
              onTreeSelect={onTreeSelect}
              onGroupAction={handleGroupAction}
              t={t}
              loading={treeLoading}
            />
          </div>
        }
        rightSection={
          <>
            <div className="w-full mb-4 flex justify-end">
              <Search
                allowClear
                enterButton
                className="w-60 mr-2"
                onSearch={handleUserSearch}
                placeholder={`${t('common.search')}...`}
              />
              <PermissionWrapper requiredPermissions={['Add User']}>
                <Button type="primary" className="mr-2" onClick={() => openUserModal('add')}>
                  +{t('common.add')}
                </Button>
              </PermissionWrapper>
              <UserModal ref={userModalRef} treeData={treeData} onSuccess={onSuccessUserModal} />
              {hasBatchActions && (
                <Dropdown
                  overlay={
                    <Menu className={`${commonStyles.batchOperationMenu} ${styles.batchOperationMenuCentered}`}>
                      {canEditUser && (
                        <Menu.Item key="enable">
                          <PermissionWrapper requiredPermissions={['Edit User']}>
                            <Button type="text" className="w-full" onClick={() => handleBatchUserStatus('enable')}>
                              {t('common.enable') || 'Enable'}
                            </Button>
                          </PermissionWrapper>
                        </Menu.Item>
                      )}
                      {canEditUser && (
                        <Menu.Item key="disable">
                          <PermissionWrapper requiredPermissions={['Edit User']}>
                            <Button type="text" className="w-full" onClick={() => handleBatchUserStatus('disable')}>
                              {t('common.disable') || 'Disable'}
                            </Button>
                          </PermissionWrapper>
                        </Menu.Item>
                      )}
                      {canEditUser && (
                        <Menu.Item key="unlock">
                          <PermissionWrapper requiredPermissions={['Edit User']}>
                            <Button type="text" className="w-full" onClick={() => handleBatchUserStatus('unlock')}>
                              {t('system.user.status.unlock') || 'Unlock'}
                            </Button>
                          </PermissionWrapper>
                        </Menu.Item>
                      )}
                      {canDeleteUser && (
                        <Menu.Item key="delete">
                          <PermissionWrapper requiredPermissions={['Delete User']}>
                            <Button type="text" className="w-full" onClick={() => handleBatchUserStatus('delete')}>
                              {t('common.delete') || 'Delete'}
                            </Button>
                          </PermissionWrapper>
                        </Menu.Item>
                      )}
                    </Menu>
                  }
                  trigger={['click']}
                  disabled={isDeleteDisabled}
                >
                  <Button>
                    {t('common.batchOperation') || 'Batch Operation'}
                    <DownOutlined />
                  </Button>
                </Dropdown>
              )}
              <PasswordModal
                ref={passwordModalRef}
                onSuccess={() => fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize })}
              />
            </div>
            <Spin spinning={loading}>
              <CustomTable
                scroll={{ y: 'calc(100vh - 430px)' }}
                pagination={{
                  pageSize,
                  current: currentPage,
                  total,
                  showSizeChanger: true,
                  onChange: handleTableChange,
                }}
                columns={columns}
                dataSource={tableData}
                rowSelection={rowSelection}
              />
            </Spin>
          </>
        }
      />

      <GroupEditModal ref={groupEditModalRef} onSuccess={onSuccessGroupEdit} />

      <OperateModal
        title={t('common.add')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: addGroupLoading }}
        cancelButtonProps={{ disabled: addGroupLoading }}
        open={addGroupModalOpen || addSubGroupModalOpen}
        onOk={onAddGroup}
        onCancel={closeGroupModals}
        destroyOnHidden={true}
      >
        <Form ref={addGroupFormRef}>
          <Form.Item
            name="name"
            label={t('system.group.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.group.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default User;
