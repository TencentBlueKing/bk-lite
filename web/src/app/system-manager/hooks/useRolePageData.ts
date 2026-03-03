import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import type { FormInstance } from 'antd';
import { useRoleApi } from '@/app/system-manager/api/application';
import type { Role, User, Menu } from '@/app/system-manager/types/application';

interface Group {
  id: number;
  name: string;
  parent_id: number;
  description?: string;
}

interface UseRoleListParams {
  clientId: string;
  t: (key: string) => string;
}

export function useRoleList({ clientId, t }: UseRoleListParams) {
  const [roleList, setRoleList] = useState<Role[]>([]);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [menuData, setMenuData] = useState<Menu[]>([]);

  const { getRoles, getAllMenus, addRole, updateRole, deleteRole } = useRoleApi();

  const fetchAllMenus = useCallback(async () => {
    const menus = await getAllMenus({ params: { client_id: clientId } });
    setMenuData(menus);
  }, [clientId, getAllMenus]);

  const fetchRoles = useCallback(async () => {
    setLoadingRoles(true);
    try {
      const roles = await getRoles({ client_id: clientId });
      setRoleList(roles);
      return roles;
    } finally {
      setLoadingRoles(false);
    }
  }, [clientId, getRoles]);

  useEffect(() => {
    fetchAllMenus();
    fetchRoles().then(roles => {
      if (roles.length > 0) {
        setSelectedRole(roles[0]);
      }
    });
  }, []);

  const handleAddRole = useCallback(async (roleName: string) => {
    await addRole({
      client_id: clientId,
      name: roleName
    });
    await fetchRoles();
    message.success(t('common.addSuccess'));
  }, [clientId, addRole, fetchRoles, t]);

  const handleUpdateRole = useCallback(async (roleId: number, roleName: string) => {
    await updateRole({
      role_id: roleId,
      role_name: roleName,
    });
    await fetchRoles();
    message.success(t('common.updateSuccess'));
  }, [updateRole, fetchRoles, t]);

  const handleDeleteRole = useCallback(async (role: Role) => {
    try {
      await deleteRole({
        role_name: role.name,
        role_id: role.id,
      });
      message.success(t('common.delSuccess'));
      await fetchRoles();
    } catch (error) {
      console.error('Failed:', error);
      message.error(t('common.delFail'));
    }
  }, [deleteRole, fetchRoles, t]);

  return {
    roleList,
    selectedRole,
    setSelectedRole,
    loadingRoles,
    menuData,
    fetchRoles,
    handleAddRole,
    handleUpdateRole,
    handleDeleteRole
  };
}

interface UseUserTabParams {
  selectedRole: Role | null;
  t: (key: string) => string;
}

export function useUserTab({ selectedRole, t }: UseUserTabParams) {
  const [tableData, setTableData] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [selectedUserKeys, setSelectedUserKeys] = useState<React.Key[]>([]);
  const [allUserList, setAllUserList] = useState<User[]>([]);
  const [allUserLoading, setAllUserLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const { getUsersByRole, getAllUser, addUser, deleteUser } = useRoleApi();

  const fetchUsersByRole = useCallback(async (role: Role, page: number, size: number, search?: string) => {
    setLoading(true);
    try {
      const data = await getUsersByRole({
        params: {
          role_id: role.id,
          search,
          page,
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
  }, [getUsersByRole]);

  const fetchAllUsers = useCallback(async () => {
    setAllUserLoading(true);
    try {
      const users = await getAllUser();
      setAllUserList(users);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setAllUserLoading(false);
    }
  }, [getAllUser, t]);

  const handleTableChange = useCallback((page: number, size?: number) => {
    if (!selectedRole) return;
    const newPageSize = size || pageSize;
    fetchUsersByRole(selectedRole, page, newPageSize);
  }, [selectedRole, pageSize, fetchUsersByRole]);

  const handleUserSearch = useCallback((value: string) => {
    if (selectedRole) {
      fetchUsersByRole(selectedRole, 1, pageSize, value);
    }
  }, [selectedRole, pageSize, fetchUsersByRole]);

  const handleAddUser = useCallback(async (userIds: number[]) => {
    await addUser({
      role_id: selectedRole?.id,
      user_ids: userIds
    });
    message.success(t('common.addSuccess'));
    if (selectedRole) {
      fetchUsersByRole(selectedRole, currentPage, pageSize);
    }
  }, [selectedRole, currentPage, pageSize, addUser, fetchUsersByRole, t]);

  const handleDeleteUser = useCallback(async (record: User) => {
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
  }, [selectedRole, currentPage, pageSize, deleteUser, fetchUsersByRole, t]);

  const handleBatchDeleteUsers = useCallback(async () => {
    if (!selectedRole || selectedUserKeys.length === 0) return false;

    try {
      setDeleteLoading(true);
      await deleteUser({
        role_id: selectedRole.id,
        user_ids: selectedUserKeys,
      });
      message.success(t('common.delSuccess'));
      fetchUsersByRole(selectedRole, currentPage, pageSize);
      setSelectedUserKeys([]);
      return true;
    } catch (error) {
      console.error('Failed to delete users in batch:', error);
      message.error(t('common.delFailed'));
      return false;
    } finally {
      setDeleteLoading(false);
    }
  }, [selectedRole, selectedUserKeys, currentPage, pageSize, deleteUser, fetchUsersByRole, t]);

  return {
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
    fetchUsersByRole,
    fetchAllUsers,
    handleTableChange,
    handleUserSearch,
    handleAddUser,
    handleDeleteUser,
    handleBatchDeleteUsers
  };
}

interface UsePermissionTabParams {
  selectedRole: Role | null;
  t: (key: string) => string;
}

export function usePermissionTab({ selectedRole, t }: UsePermissionTabParams) {
  const [permissionsCheckedKeys, setPermissionsCheckedKeys] = useState<{ [key: string]: string[] }>({});
  const [loading, setLoading] = useState(false);

  const { getRoleMenus, setRoleMenus } = useRoleApi();

  const fetchRolePermissions = useCallback(async (role: Role) => {
    setLoading(true);
    try {
      const permissions = await getRoleMenus({ params: { role_id: role.id } });
      const permissionsMap: Record<string, string[]> = permissions.reduce((acc: Record<string, string[]>, item: string) => {
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
  }, [getRoleMenus, t]);

  const handleConfirmPermissions = useCallback(async () => {
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
  }, [selectedRole, permissionsCheckedKeys, setRoleMenus, t]);

  return {
    permissionsCheckedKeys,
    setPermissionsCheckedKeys,
    loading,
    fetchRolePermissions,
    handleConfirmPermissions
  };
}

interface UseOrganizationTabParams {
  selectedRole: Role | null;
  t: (key: string) => string;
}

export function useOrganizationTab({ selectedRole, t }: UseOrganizationTabParams) {
  const [groupTableData, setGroupTableData] = useState<Group[]>([]);
  const [loading, setLoading] = useState(false);
  const [groupCurrentPage, setGroupCurrentPage] = useState(1);
  const [groupPageSize, setGroupPageSize] = useState(10);
  const [groupTotal, setGroupTotal] = useState(0);
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<React.Key[]>([]);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const { getRoleGroups, addRoleGroups, deleteRoleGroups } = useRoleApi();

  const fetchRoleGroups = useCallback(async (role: Role, page: number, size: number, search?: string) => {
    setLoading(true);
    try {
      const data = await getRoleGroups({
        params: {
          role_id: role.id,
          search,
          page,
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
  }, [getRoleGroups]);

  const handleGroupTableChange = useCallback((page: number, size?: number) => {
    if (!selectedRole) return;
    const newPageSize = size || groupPageSize;
    fetchRoleGroups(selectedRole, page, newPageSize);
  }, [selectedRole, groupPageSize, fetchRoleGroups]);

  const handleGroupSearch = useCallback((value: string) => {
    if (selectedRole) {
      fetchRoleGroups(selectedRole, 1, groupPageSize, value);
    }
  }, [selectedRole, groupPageSize, fetchRoleGroups]);

  const handleAddGroups = useCallback(async (groupIds: number[]) => {
    await addRoleGroups({
      role_id: selectedRole?.id.toString(),
      group_ids: groupIds.map(id => id.toString())
    });
    message.success(t('common.addSuccess'));
    if (selectedRole) {
      fetchRoleGroups(selectedRole, groupCurrentPage, groupPageSize);
    }
  }, [selectedRole, groupCurrentPage, groupPageSize, addRoleGroups, fetchRoleGroups, t]);

  const handleDeleteGroup = useCallback(async (record: Group) => {
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
  }, [selectedRole, groupCurrentPage, groupPageSize, deleteRoleGroups, fetchRoleGroups, t]);

  const handleBatchDeleteGroups = useCallback(async () => {
    if (!selectedRole || selectedGroupKeys.length === 0) return false;

    try {
      setDeleteLoading(true);
      await deleteRoleGroups({
        role_id: selectedRole.id.toString(),
        group_ids: selectedGroupKeys.map(key => key.toString())
      });
      message.success(t('common.delSuccess'));
      fetchRoleGroups(selectedRole, groupCurrentPage, groupPageSize);
      setSelectedGroupKeys([]);
      return true;
    } catch (error) {
      console.error('Failed to delete groups in batch:', error);
      message.error(t('common.delFailed'));
      return false;
    } finally {
      setDeleteLoading(false);
    }
  }, [selectedRole, selectedGroupKeys, groupCurrentPage, groupPageSize, deleteRoleGroups, fetchRoleGroups, t]);

  return {
    groupTableData,
    loading,
    groupCurrentPage,
    groupPageSize,
    groupTotal,
    selectedGroupKeys,
    setSelectedGroupKeys,
    deleteLoading,
    fetchRoleGroups,
    handleGroupTableChange,
    handleGroupSearch,
    handleAddGroups,
    handleDeleteGroup,
    handleBatchDeleteGroups
  };
}

interface UseRoleModalParams {
  roleForm: FormInstance;
  handleAddRole: (name: string) => Promise<void>;
  handleUpdateRole: (roleId: number, name: string) => Promise<void>;
}

export function useRoleModal({ roleForm, handleAddRole, handleUpdateRole }: UseRoleModalParams) {
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [isEditingRole, setIsEditingRole] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [modalLoading, setModalLoading] = useState(false);

  const showRoleModal = useCallback((role: Role | null = null) => {
    setIsEditingRole(!!role);
    setEditingRole(role);
    if (role) {
      roleForm.setFieldsValue({ roleName: role.name });
    } else {
      roleForm.resetFields();
    }
    setRoleModalOpen(true);
  }, [roleForm]);

  const handleRoleModalSubmit = useCallback(async () => {
    setModalLoading(true);
    try {
      await roleForm.validateFields();
      const roleName = roleForm.getFieldValue('roleName');
      if (isEditingRole && editingRole) {
        await handleUpdateRole(editingRole.id, roleName);
      } else {
        await handleAddRole(roleName);
      }
      setRoleModalOpen(false);
    } catch (error) {
      console.error('Failed:', error);
    } finally {
      setModalLoading(false);
    }
  }, [roleForm, isEditingRole, editingRole, handleAddRole, handleUpdateRole]);

  return {
    roleModalOpen,
    setRoleModalOpen,
    isEditingRole,
    modalLoading,
    showRoleModal,
    handleRoleModalSubmit
  };
}
