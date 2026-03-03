"use client";
import React, { useState, useCallback } from 'react';
import { Button, Input, Form, Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from "@/components/permission";
import PermissionTable from './permissionTable';
import RoleList from './roleList';
import UserTab from './UserTab';
import OrganizationTab from './OrganizationTab';
import type { Role } from '@/app/system-manager/types/application';
import {
  useRoleList,
  useUserTab,
  usePermissionTab,
  useOrganizationTab,
  useRoleModal
} from '@/app/system-manager/hooks/useRolePageData';

const { TabPane } = Tabs;

const RoleManagement: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const clientId = searchParams?.get('clientId') || '';

  const [roleForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('1');
  const [addUserModalOpen, setAddUserModalOpen] = useState(false);
  const [addGroupModalOpen, setAddGroupModalOpen] = useState(false);
  const [userModalLoading, setUserModalLoading] = useState(false);
  const [groupModalLoading, setGroupModalLoading] = useState(false);

  const {
    roleList,
    selectedRole,
    setSelectedRole,
    loadingRoles,
    menuData,
    handleAddRole,
    handleUpdateRole,
    handleDeleteRole
  } = useRoleList({ clientId, t });

  const userTab = useUserTab({ selectedRole, t });
  const permissionTab = usePermissionTab({ selectedRole, t });
  const organizationTab = useOrganizationTab({ selectedRole, t });

  const {
    roleModalOpen,
    setRoleModalOpen,
    isEditingRole,
    modalLoading,
    showRoleModal,
    handleRoleModalSubmit
  } = useRoleModal({ roleForm, handleAddRole, handleUpdateRole });

  const handleTabChange = useCallback((key: string) => {
    setActiveTab(key);
    if (selectedRole) {
      if (key === '1') {
        userTab.fetchUsersByRole(selectedRole, 1, userTab.pageSize);
      } else if (key === '2') {
        permissionTab.fetchRolePermissions(selectedRole);
      } else if (key === '3') {
        organizationTab.fetchRoleGroups(selectedRole, 1, organizationTab.groupPageSize);
      }
    }
  }, [selectedRole, userTab, permissionTab, organizationTab]);

  const onSelectRole = useCallback((role: Role) => {
    setSelectedRole(role);
    if (activeTab === '2' || role.name === 'admin') {
      setActiveTab('1');
      userTab.fetchUsersByRole(role, 1, userTab.pageSize);
      return;
    }
    if (activeTab === '1') {
      userTab.fetchUsersByRole(role, 1, userTab.pageSize);
    } else if (activeTab === '2') {
      permissionTab.fetchRolePermissions(role);
    } else if (activeTab === '3') {
      organizationTab.fetchRoleGroups(role, 1, organizationTab.groupPageSize);
    }
  }, [activeTab, userTab, permissionTab, organizationTab, setSelectedRole]);

  const handleAddUserWrapper = useCallback(async (userIds: number[]) => {
    setUserModalLoading(true);
    try {
      await userTab.handleAddUser(userIds);
    } finally {
      setUserModalLoading(false);
    }
  }, [userTab]);

  const handleAddGroupsWrapper = useCallback(async (groupIds: number[]) => {
    setGroupModalLoading(true);
    try {
      await organizationTab.handleAddGroups(groupIds);
    } finally {
      setGroupModalLoading(false);
    }
  }, [organizationTab]);

  return (
    <>
      <div className="w-full flex justify-between bg-[var(--color-bg)] rounded-md h-full p-4">
        <RoleList
          loadingRoles={loadingRoles}
          roleList={roleList}
          selectedRole={selectedRole}
          onSelectRole={onSelectRole}
          showRoleModal={showRoleModal}
          onDeleteRole={handleDeleteRole}
          t={t}
        />
        <div className="flex-1 overflow-hidden rounded-md">
          <Tabs defaultActiveKey="1" activeKey={activeTab} onChange={handleTabChange}>
            <TabPane tab={t('system.role.users')} key="1">
              <UserTab
                tableData={userTab.tableData}
                loading={userTab.loading}
                currentPage={userTab.currentPage}
                pageSize={userTab.pageSize}
                total={userTab.total}
                selectedUserKeys={userTab.selectedUserKeys}
                setSelectedUserKeys={userTab.setSelectedUserKeys}
                allUserList={userTab.allUserList}
                allUserLoading={userTab.allUserLoading}
                deleteLoading={userTab.deleteLoading}
                addUserModalOpen={addUserModalOpen}
                setAddUserModalOpen={setAddUserModalOpen}
                modalLoading={userModalLoading}
                t={t}
                onSearch={userTab.handleUserSearch}
                onTableChange={userTab.handleTableChange}
                onAddUser={handleAddUserWrapper}
                onDeleteUser={userTab.handleDeleteUser}
                onBatchDelete={userTab.handleBatchDeleteUsers}
                onFetchAllUsers={userTab.fetchAllUsers}
              />
            </TabPane>
            {selectedRole?.name !== 'admin' && (
              <TabPane tab={t('system.role.permissions')} key="2">
                <div className="flex justify-end items-center mb-4">
                  <PermissionWrapper requiredPermissions={['Edit Permission']}>
                    <Button
                      type="primary"
                      loading={permissionTab.loading}
                      onClick={permissionTab.handleConfirmPermissions}
                    >
                      {t('common.confirm')}
                    </Button>
                  </PermissionWrapper>
                </div>
                <PermissionTable
                  t={t}
                  loading={permissionTab.loading}
                  menuData={menuData}
                  permissionsCheckedKeys={permissionTab.permissionsCheckedKeys}
                  setPermissionsCheckedKeys={permissionTab.setPermissionsCheckedKeys}
                />
              </TabPane>
            )}
            <TabPane tab={t('system.role.organizations')} key="3">
              <OrganizationTab
                groupTableData={organizationTab.groupTableData}
                loading={organizationTab.loading}
                groupCurrentPage={organizationTab.groupCurrentPage}
                groupPageSize={organizationTab.groupPageSize}
                groupTotal={organizationTab.groupTotal}
                selectedGroupKeys={organizationTab.selectedGroupKeys}
                setSelectedGroupKeys={organizationTab.setSelectedGroupKeys}
                deleteLoading={organizationTab.deleteLoading}
                addGroupModalOpen={addGroupModalOpen}
                setAddGroupModalOpen={setAddGroupModalOpen}
                modalLoading={groupModalLoading}
                t={t}
                onSearch={organizationTab.handleGroupSearch}
                onTableChange={organizationTab.handleGroupTableChange}
                onAddGroups={handleAddGroupsWrapper}
                onDeleteGroup={organizationTab.handleDeleteGroup}
                onBatchDelete={organizationTab.handleBatchDeleteGroups}
              />
            </TabPane>
          </Tabs>
        </div>
      </div>
      <OperateModal
        title={isEditingRole ? t('system.role.updateRole') : t('system.role.addRole')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={roleModalOpen}
        onOk={handleRoleModalSubmit}
        onCancel={() => setRoleModalOpen(false)}
      >
        <Form form={roleForm}>
          <Form.Item
            name="roleName"
            label={t('system.role.name')}
            rules={[{ required: true, message: `${t('common.inputMsg')}${t('system.role.name')}` }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.role.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default RoleManagement;
