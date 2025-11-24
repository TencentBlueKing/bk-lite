"use client";
import React, { useState, useEffect } from 'react';
import { Button, Input, Form, message, Spin, Popconfirm, Tabs, Select, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useRoleApi } from '@/app/system-manager/api/application';
import { Role, User, Menu } from '@/app/system-manager/types/application';
import PermissionTable from './permissionTable';
import PermissionWrapper from "@/components/permission";
import RoleList from './roleList';
import GroupTreeSelect from '@/components/group-tree-select';

const { Search } = Input;
const { TabPane } = Tabs;
const { Option } = Select;
const { confirm } = Modal;

// 组织数据类型定义
interface Group {
  id: number;
  name: string;
  parent_id: number;
  description?: string;
}

const RoleManagement: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const clientId = searchParams?.get('clientId') || '';

  const [roleForm] = Form.useForm();
  const [addUserForm] = Form.useForm();
  const [addGroupForm] = Form.useForm();

  const [roleList, setRoleList] = useState<Role[]>([]);
  const [allUserList, setAllUserList] = useState<User[]>([]);
  const [tableData, setTableData] = useState<User[]>([]);
  const [groupTableData, setGroupTableData] = useState<Group[]>([]);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [loading, setLoading] = useState(false);
  const [allUserLoading, setAllUserLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [addUserModalOpen, setAddUserModalOpen] = useState(false);
  const [addGroupModalOpen, setAddGroupModalOpen] = useState(false);
  const [selectedUserKeys, setSelectedUserKeys] = useState<React.Key[]>([]);
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<React.Key[]>([]);
  const [permissionsCheckedKeys, setPermissionsCheckedKeys] = useState<{ [key: string]: string[] }>({});
  const [isEditingRole, setIsEditingRole] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [groupCurrentPage, setGroupCurrentPage] = useState(1);
  const [groupPageSize, setGroupPageSize] = useState(10);
  const [groupTotal, setGroupTotal] = useState(0);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('1');
  const [menuData, setMenuData] = useState<Menu[]>([]);

  const {
    getRoles,
    getUsersByRole,
    getAllUser,
    getRoleMenus,
    updateRole,
    addRole,
    addUser,
    deleteRole,
    deleteUser,
    setRoleMenus,
    getAllMenus,
    getRoleGroups,
    addRoleGroups,
    deleteRoleGroups
  } = useRoleApi();

  useEffect(() => {
    fetchAllMenus();
    fetchRoles();
  }, []);

  const fetchRoles = async () => {
    setLoadingRoles(true);
    try {
      const roles = await getRoles({ client_id: clientId });
      setRoleList(roles);
      if (roles.length > 0) {
        setSelectedRole(roles[0]);
        fetchUsersByRole(roles[0], 1, pageSize);
      }
    } finally {
      setLoadingRoles(false);
    }
  };

  const fetchAllMenus = async () => {
    const menus = await getAllMenus({ params: { client_id: clientId } });
    setMenuData(menus);
  };

  const fetchUsersByRole = async (role: Role, page: number, size: number, search?: string) => {
    setLoading(true);
    try {
      const data = await getUsersByRole({
        params: {
          role_id: role.id,
          search,
          page: page, 
          page_size: size
        },
      });
      setTableData(data.items || []);
      setTotal(data.count);
      setCurrentPage(page);
      setPageSize(size);
    } finally {
      setLoading(false);
    }
  };

  const fetchRoleGroups = async (role: Role, page: number, size: number, search?: string) => {
    setLoading(true);
    try {
      const data = await getRoleGroups({
        params: {
          role_id: role.id,
          search,
          page: page,
          page_size: size
        },
      });
      setGroupTableData(data.items || []);
      setGroupTotal(data.count);
      setGroupCurrentPage(page);
      setGroupPageSize(size);
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (page: number, size?: number) => {
    if (!selectedRole) return;
    const newPageSize = size || pageSize;
    fetchUsersByRole(selectedRole, page, newPageSize);
  };

  const handleGroupTableChange = (page: number, size?: number) => {
    if (!selectedRole) return;
    const newPageSize = size || groupPageSize;
    fetchRoleGroups(selectedRole, page, newPageSize);
  };

  const fetchAllUsers = async () => {
    setAllUserLoading(true);
    try {
      const users = await getAllUser();
      setAllUserList(users);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setAllUserLoading(false);
    }
  };

  const fetchRolePermissions = async (role: Role) => {
    setLoading(true);
    try {
      const permissions = await getRoleMenus({ params: { role_id: role.id } });
      const permissionsMap: Record<string, string[]> = permissions.reduce((acc: any, item: string) => {
        const [name, ...operations] = item.split('-');
        if (!acc[name]) acc[name] = [];
        acc[name].push(...operations);
        return acc;
      }, {});
      setPermissionsCheckedKeys(permissionsMap);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setLoading(false);
    }
  };

  const showRoleModal = (role: Role | null = null) => {
    setIsEditingRole(!!role);
    setSelectedRole(role);
    if (role) {
      roleForm.setFieldsValue({ roleName: role.name });
    } else {
      roleForm.resetFields();
    }
    setRoleModalOpen(true);
  };

  const handleRoleModalSubmit = async () => {
    setModalLoading(true);
    try {
      await roleForm.validateFields();
      const roleName = roleForm.getFieldValue('roleName');
      if (isEditingRole && selectedRole) {
        await updateRole({
          role_id: selectedRole.id,
          role_name: roleName,
        });
      } else {
        await addRole({
          client_id: clientId,
          name: roleName
        });
      }
      await fetchRoles();
      message.success(isEditingRole ? t('common.updateSuccess') : t('common.addSuccess'));
      setRoleModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    } finally {
      setModalLoading(false);
    }
  };

  const onDeleteRole = async (role: Role) => {
    try {
      await deleteRole({
        role_name: role.name,
        role_id: role.id,
      });
      message.success(t('common.delSuccess'));
      await fetchRoles();
      if (selectedRole) await fetchUsersByRole(selectedRole, 1, pageSize);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  };

  const columns = [
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
      render: (_: any, record: User) => (
        <PermissionWrapper requiredPermissions={['Remove user']}>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => handleDeleteUser(record)}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </PermissionWrapper>
      ),
    },
  ];

  const groupColumns = [
    {
      title: t('system.role.organizationName'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: any, record: Group) => (
        <PermissionWrapper requiredPermissions={['Remove group']}>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => handleDeleteGroup(record)}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </PermissionWrapper>
      ),
    },
  ];

  const handleBatchDeleteUsers = async () => {
    if (!selectedRole || selectedUserKeys.length === 0) return;

    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        try {
          setDeleteLoading(true);
          await deleteUser({
            role_id: selectedRole.id,
            user_ids: selectedUserKeys,
          });
          message.success(t('common.delSuccess'));

          fetchUsersByRole(selectedRole, currentPage, pageSize);
          setSelectedUserKeys([]);
        } catch (error) {
          console.error('Failed to delete users in batch:', error);
          message.error(t('common.delFailed'));
        } finally {
          setDeleteLoading(false);
        }
      },
    });
  };

  const handleBatchDeleteGroups = async () => {
    if (!selectedRole || selectedGroupKeys.length === 0) return;

    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        try {
          setDeleteLoading(true);
          await deleteRoleGroups({
            role_id: selectedRole.id.toString(),
            group_ids: selectedGroupKeys.map(key => key.toString())
          });
          message.success(t('common.delSuccess'));
          fetchRoleGroups(selectedRole, groupCurrentPage, groupPageSize);
          setSelectedGroupKeys([]);
        } catch (error) {
          console.error('Failed to delete groups in batch:', error);
          message.error(t('common.delFailed'));
        } finally {
          setDeleteLoading(false);
        }
      },
    });
  };

  const handleDeleteUser = async (record: User) => {
    if (!selectedRole) return;
    try {
      await deleteUser({
        role_id: selectedRole.id,
        user_ids: [record.id]
      });
      message.success(t('common.delSuccess'));
      fetchUsersByRole(selectedRole, currentPage, pageSize);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  };

  const handleDeleteGroup = async (record: Group) => {
    if (!selectedRole) return;
    try {
      await deleteRoleGroups({
        role_id: selectedRole.id.toString(),
        group_ids: [record.id.toString()]
      });
      message.success(t('common.delSuccess'));
      fetchRoleGroups(selectedRole, groupCurrentPage, groupPageSize);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  };

  const onSelectRole = (role: Role) => {
    setSelectedRole(role);
    if (activeTab === '2' || role.name === 'admin') {
      setActiveTab('1');
      fetchUsersByRole(role, 1, pageSize);
      return;
    }
    if (activeTab === '1') {
      fetchUsersByRole(role, 1, pageSize);
    } else if (activeTab === '2') {
      fetchRolePermissions(role);
    } else if (activeTab === '3') {
      fetchRoleGroups(role, 1, groupPageSize);
    }
  };

  const handleConfirmPermissions = async () => {
    if (!selectedRole) return;

    setLoading(true);
    try {
      const menus = Object.entries(permissionsCheckedKeys).flatMap(([menuName, operations]) =>
        operations.map(operation => `${menuName}-${operation}`)
      );
      await setRoleMenus({
        role_id: selectedRole.id,
        role_name: selectedRole.name,
        menus
      });
      message.success(t('common.updateSuccess'));
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.updateFail'));
    } finally {
      setLoading(false);
    }
  };

  const handleUserSearch = (value: string) => {
    fetchUsersByRole(selectedRole!, 1, pageSize, value);
  };

  const handleGroupSearch = (value: string) => {
    fetchRoleGroups(selectedRole!, 1, groupPageSize, value);
  };

  const openUserModal = () => {
    if (!allUserList.length) fetchAllUsers();
    addUserForm.resetFields();
    setAddUserModalOpen(true);
  };

  const openGroupModal = () => {
    addGroupForm.resetFields();
    setAddGroupModalOpen(true);
  };

  const handleAddUser = async () => {
    setModalLoading(true);
    try {
      const values = await addUserForm.validateFields();
      await addUser({
        role_id: selectedRole?.id,
        user_ids: values.users
      });
      message.success(t('common.addSuccess'));
      fetchUsersByRole(selectedRole!, currentPage, pageSize);
      setAddUserModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.saveFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleAddGroups = async () => {
    setModalLoading(true);
    try {
      const values = await addGroupForm.validateFields();
      await addRoleGroups({
        role_id: selectedRole?.id.toString(),
        group_ids: values.groups.map((id: any) => id.toString())
      });
      message.success(t('common.addSuccess'));
      fetchRoleGroups(selectedRole!, groupCurrentPage, groupPageSize);
      setAddGroupModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.saveFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (selectedRole) {
      if (key === '1') {
        fetchUsersByRole(selectedRole, 1, pageSize);
      } else if (key === '2') {
        fetchRolePermissions(selectedRole);
      } else if (key === '3') {
        fetchRoleGroups(selectedRole, 1, groupPageSize);
      }
    }
  };

  return (
    <>
      <div className="w-full flex justify-between bg-[var(--color-bg)] rounded-md h-full p-4">
        <RoleList
          loadingRoles={loadingRoles}
          roleList={roleList}
          selectedRole={selectedRole}
          onSelectRole={onSelectRole}
          showRoleModal={showRoleModal}
          onDeleteRole={onDeleteRole}
          t={t}
        />
        <div className="flex-1 overflow-hidden rounded-md">
          <Tabs defaultActiveKey="1" activeKey={activeTab} onChange={handleTabChange}>
            <TabPane tab={t('system.role.users')} key="1">
              <div className="flex justify-end mb-4">
                <Search
                  allowClear
                  enterButton
                  className='w-60 mr-[8px]'
                  onSearch={handleUserSearch}
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
                    onClick={handleBatchDeleteUsers}
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
                    onChange: handleTableChange,
                  }}
                />
              </Spin>
            </TabPane>
            {selectedRole?.name !== 'admin' && (
              <TabPane tab={t('system.role.permissions')} key="2">
                <div className="flex justify-end items-center mb-4">
                  <PermissionWrapper requiredPermissions={['Edit Permission']}>
                    <Button type="primary" loading={loading} onClick={handleConfirmPermissions}>{t('common.confirm')}</Button>
                  </PermissionWrapper>
                </div>
                <PermissionTable
                  t={t}
                  loading={loading}
                  menuData={menuData}
                  permissionsCheckedKeys={permissionsCheckedKeys}
                  setPermissionsCheckedKeys={(keyMap) => setPermissionsCheckedKeys(keyMap)}
                />
              </TabPane>
            )}
            <TabPane tab={t('system.role.organizations')} key="3">
              <div className="flex justify-end mb-4">
                <Search
                  allowClear
                  enterButton
                  className='w-60 mr-[8px]'
                  onSearch={handleGroupSearch}
                  placeholder={`${t('common.search')}`}
                />
                <PermissionWrapper requiredPermissions={['Add group']}>
                  <Button
                    className="mr-[8px]"
                    type="primary"
                    onClick={openGroupModal}
                  >
                    +{t('common.add')}
                  </Button>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['Remove group']}>
                  <Button
                    loading={deleteLoading}
                    onClick={handleBatchDeleteGroups}
                    disabled={selectedGroupKeys.length === 0 || deleteLoading}
                  >
                    {t('system.common.modifydelete')}
                  </Button>
                </PermissionWrapper>
              </div>
              <Spin spinning={loading}>
                <CustomTable
                  scroll={{ y: 'calc(100vh - 435px)' }}
                  rowSelection={{
                    selectedRowKeys: selectedGroupKeys,
                    onChange: (selectedRowKeys) => setSelectedGroupKeys(selectedRowKeys as React.Key[]),
                  }}
                  columns={groupColumns}
                  dataSource={groupTableData}
                  rowKey={(record) => record.id}
                  pagination={{
                    current: groupCurrentPage,
                    pageSize: groupPageSize,
                    total: groupTotal,
                    onChange: handleGroupTableChange,
                  }}
                />
              </Spin>
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

      <OperateModal
        title={t('system.role.addOrganization')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: modalLoading }}
        cancelButtonProps={{ disabled: modalLoading }}
        open={addGroupModalOpen}
        onOk={handleAddGroups}
        onCancel={() => setAddGroupModalOpen(false)}
      >
        <div className="mb-4 p-3 bg-blue-50 rounded-md border border-blue-200">
          <div className="text-blue-800 text-sm">
            {t('system.role.organizationTip')}
          </div>
        </div>
        <Form form={addGroupForm}>
          <Form.Item
            name="groups"
            label={t('system.role.organizations')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <GroupTreeSelect
              placeholder={`${t('common.select')}${t('system.role.organizations')}`}
              multiple={true}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default RoleManagement;
