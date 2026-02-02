'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { message, Modal } from 'antd';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useRoleApi } from '@/app/system-manager/api/application';

interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string;
  is_superuser: boolean;
  last_login?: string;
  created_at?: string;
}

interface UseAdminUsersListReturn {
  loading: boolean;
  adminUsers: AdminUser[];
  currentPage: number;
  pageSize: number;
  total: number;
  fetchAdminUsers: (params?: { page?: number; page_size?: number }) => Promise<void>;
  handleTableChange: (page: number, newPageSize?: number) => void;
}

export function useAdminUsersList(t: (key: string) => string): UseAdminUsersListReturn {
  const { getUsersList } = useUserApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [total, setTotal] = useState<number>(0);

  const isInitializedRef = useRef(false);
  const fetchingRef = useRef(false);

  const fetchAdminUsers = useCallback(
    async (params: { page?: number; page_size?: number } = {}) => {
      if (fetchingRef.current) return;

      fetchingRef.current = true;
      setLoading(true);
      try {
        const res = await getUsersList({
          is_superuser: 1,
          page: params.page || currentPage,
          page_size: params.page_size || pageSize,
          ...params,
        });

        const data = res.users.map((item: AdminUser) => ({
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
    },
    [currentPage, pageSize, getUsersList, t]
  );

  const handleTableChange = useCallback(
    (page: number, newPageSize?: number) => {
      const finalPageSize = newPageSize || pageSize;
      setCurrentPage(page);
      if (newPageSize && newPageSize !== pageSize) {
        setPageSize(newPageSize);
      }
      fetchAdminUsers({ page, page_size: finalPageSize });
    },
    [pageSize, fetchAdminUsers]
  );

  useEffect(() => {
    if (isInitializedRef.current) return;
    isInitializedRef.current = true;
    fetchAdminUsers();
  }, []);

  return {
    loading,
    adminUsers,
    currentPage,
    pageSize,
    total,
    fetchAdminUsers,
    handleTableChange,
  };
}

interface UseAdminActionsReturn {
  handleRevokeAdmin: (userId: string) => void;
}

export function useAdminActions(
  t: (key: string) => string,
  onSuccess: () => void
): UseAdminActionsReturn {
  const { deleteUser } = useRoleApi();
  const { confirm } = Modal;

  const handleRevokeAdmin = useCallback(
    (userId: string) => {
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
              is_superuser: true,
            });
            message.success(t('system.administrator.revokeSuccess'));
            onSuccess();
          } catch {
            message.error(t('system.administrator.revokeFailed'));
          }
        },
      });
    },
    [confirm, deleteUser, t, onSuccess]
  );

  return {
    handleRevokeAdmin,
  };
}

interface UseAddAdminModalReturn {
  addAdminModalOpen: boolean;
  selectedUsers: string[];
  addAdminLoading: boolean;
  modalLoading: boolean;
  normalUsers: AdminUser[];
  setSelectedUsers: (users: string[]) => void;
  openAddAdminModal: () => void;
  closeAddAdminModal: () => void;
  handleAddAdmin: () => Promise<void>;
}

export function useAddAdminModal(
  adminUsers: AdminUser[],
  t: (key: string) => string,
  onSuccess: () => void
): UseAddAdminModalReturn {
  const { getAllUser, addUser } = useRoleApi();
  const [addAdminModalOpen, setAddAdminModalOpen] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [addAdminLoading, setAddAdminLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [normalUsers, setNormalUsers] = useState<AdminUser[]>([]);

  const fetchAllUsers = useCallback(async () => {
    setAddAdminLoading(true);
    try {
      const allUsers = await getAllUser();

      const adminUserIds = new Set(adminUsers.map((admin) => admin.id));
      const availableUsers = allUsers
        .filter((item: AdminUser) => !item.is_superuser && !adminUserIds.has(item.id))
        .map((item: AdminUser) => ({
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
  }, [adminUsers, getAllUser, t]);

  const openAddAdminModal = useCallback(() => {
    if (!normalUsers.length) fetchAllUsers();
    setAddAdminModalOpen(true);
  }, [normalUsers.length, fetchAllUsers]);

  const closeAddAdminModal = useCallback(() => {
    setAddAdminModalOpen(false);
    setSelectedUsers([]);
  }, []);

  const handleAddAdmin = useCallback(async () => {
    if (selectedUsers.length === 0) {
      message.warning(t('system.administrator.pleaseSelectUser'));
      return;
    }

    setModalLoading(true);
    try {
      await addUser({
        user_ids: selectedUsers,
        is_superuser: true,
      });
      message.success(t('system.administrator.addSuccess'));
      setAddAdminModalOpen(false);
      setSelectedUsers([]);
      onSuccess();
    } catch (error) {
      console.error('Failed to add admin:', error);
      message.error(t('system.administrator.addFailed'));
    } finally {
      setModalLoading(false);
    }
  }, [selectedUsers, addUser, t, onSuccess]);

  return {
    addAdminModalOpen,
    selectedUsers,
    addAdminLoading,
    modalLoading,
    normalUsers,
    setSelectedUsers,
    openAddAdminModal,
    closeAddAdminModal,
    handleAddAdmin,
  };
}
