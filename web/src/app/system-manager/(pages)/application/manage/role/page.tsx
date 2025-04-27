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
import RoleList from './roleList';

const { Search } = Input;
const { TabPane } = Tabs;
const { Option } = Select;
const { confirm } = Modal;

const RoleManagement: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams?.get('id') || '';
  const clientId = searchParams?.get('clientId') || '';

  const [roleForm] = Form.useForm();
  const [addUserForm] = Form.useForm();

  const [roleList, setRoleList] = useState<Role[]>([]);
  const [userList, setUserList] = useState<User[]>([]);
  const [allUserList, setAllUserList] = useState<User[]>([]);
  const [tableData, setTableData] = useState<User[]>([]);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [loading, setLoading] = useState(false);
  const [allUserLoading, setAllUserLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [addUserModalOpen, setAddUserModalOpen] = useState(false);
  const [selectedUserKeys, setSelectedUserKeys] = useState<React.Key[]>([]);
  const [permissionsCheckedKeys, setPermissionsCheckedKeys] = useState<{ [key: string]: string[] }>({});
  const [isEditingRole, setIsEditingRole] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
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
    getAllMenus
  } = useRoleApi();

  useEffect(() => {
    fetchAllMenus();
    fetchRoles();
  }, []);

  const fetchRoles = async () => {
    setLoadingRoles(true);
    try {
      const roles = await getRoles({ client_id: id });
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
    const menus = await getAllMenus({ params: { client_id: id } });
    setMenuData(menus);
  };

  const fetchUsersByRole = async (role: Role, page: number, size: number, search?: string) => {
    setLoading(true);
    try {
      const users = await getUsersByRole({
        params: {
          role_id: role.role_id,
          client_id: id,
          search,
        },
      });
      setUserList(users);
      handleTableChange(page, size, users);
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (page: number, size?: number, listOverride?: User[]) => {
    const newPageSize = size || pageSize;
    const offset = (page - 1) * newPageSize;
    const currentList = listOverride || userList;
    const paginatedData = currentList.slice(offset, offset + newPageSize);

    setTableData(paginatedData);
    setCurrentPage(page);
    setPageSize(newPageSize);
    setTotal(listOverride?.length || userList.length);
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
      const permissions = await getRoleMenus({ params: { id, policy_id: role.policy_id } });
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
      roleForm.setFieldsValue({ roleName: role.display_name });
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
          role_id: selectedRole.role_id,
          policy_id: selectedRole.policy_id,
          policy_name: roleName,
          id
        });
      } else {
        await addRole({
          client_id: clientId,
          name: roleName,
          id
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
        policy_id: role.policy_id,
        display_name: role.display_name,
        role_name: role.role_name,
        id
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
      dataIndex: 'lastName',
      key: 'lastName',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: any, record: User) => (
        <Popconfirm
          title={t('common.delConfirm')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          onConfirm={() => handleDeleteUser(record)}
        >
          <Button type="link">{t('common.delete')}</Button>
        </Popconfirm>
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
            role_id: selectedRole.role_id,
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

  const handleDeleteUser = async (record: User) => {
    if (!selectedRole) return;
    try {
      await deleteUser({
        role_id: selectedRole.role_id,
        user_ids: [record.id]
      });
      message.success(t('common.delSuccess'));
      fetchUsersByRole(selectedRole, currentPage, pageSize);
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  };

  const onSelectRole = (role: Role) => {
    setSelectedRole(role);
    if (activeTab === '2' || role.display_name === 'admin') {
      setActiveTab('1');
      fetchUsersByRole(role, 1, pageSize);
      return;
    }
    if (activeTab === '1') {
      fetchUsersByRole(role, 1, pageSize);
    } else if (activeTab === '2') {
      fetchRolePermissions(role);
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
        policy_id: selectedRole.policy_id,
        policy_name: selectedRole.display_name,
        id,
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

  const openUserModal = () => {
    if (!allUserList.length) fetchAllUsers();
    addUserForm.resetFields();
    setAddUserModalOpen(true);
  };

  const handleAddUser = async () => {
    setModalLoading(true);
    try {
      const values = await addUserForm.validateFields();
      await addUser({
        role_id: selectedRole?.role_id,
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

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (selectedRole) {
      if (key === '1') {
        fetchUsersByRole(selectedRole, 1, pageSize);
      } else if (key === '2') {
        fetchRolePermissions(selectedRole);
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
                <Button
                  className="mr-[8px]"
                  type="primary"
                  onClick={openUserModal}
                >
                  +{t('common.add')}
                </Button>
                <Button
                  loading={deleteLoading}
                  onClick={handleBatchDeleteUsers}
                  disabled={selectedUserKeys.length === 0 || deleteLoading}
                >
                  {t('system.common.modifydelete')}
                </Button>
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
            {selectedRole?.display_name !== 'admin' && (
              <TabPane tab={t('system.role.permissions')} key="2">
                <div className="flex justify-end items-center mb-4">
                  <Button type="primary" loading={loading} onClick={handleConfirmPermissions}>{t('common.confirm')}</Button>
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
                <Option key={user.id} value={user.id} label={user.username}>{user.username}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default RoleManagement;
