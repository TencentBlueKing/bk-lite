'use client';

import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useRoleApi } from '@/app/system-manager/api/application';
import { useMenus } from '@/context/menus';
import type { CustomMenu, CustomMenuListParams } from '@/app/system-manager/types/menu';

interface UseCustomMenuListReturn {
  dataList: CustomMenu[];
  loading: boolean;
  pagination: { current: number; pageSize: number; total: number };
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  setPagination: React.Dispatch<React.SetStateAction<{ current: number; pageSize: number; total: number }>>;
  loadMenus: (page?: number, search?: string) => Promise<void>;
  handleSearch: (value: string) => void;
}

export function useCustomMenuList(clientId: string): UseCustomMenuListReturn {
  const { getCustomMenus } = useRoleApi();
  const [dataList, setDataList] = useState<CustomMenu[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [searchTerm, setSearchTerm] = useState('');

  const loadMenus = useCallback(
    async (page = 1, search = '') => {
      if (!clientId) return;

      setLoading(true);
      try {
        const params: CustomMenuListParams = {
          app: clientId,
          page,
          page_size: pagination.pageSize,
        };

        if (search) {
          params.search = search;
        }

        const response = await getCustomMenus({ params });
        setDataList(response.items || []);
        setPagination((prev) => ({
          ...prev,
          current: page,
          total: response.count || 0,
        }));
      } catch (error) {
        console.error('Failed to load custom menus:', error);
      } finally {
        setLoading(false);
      }
    },
    [clientId, pagination.pageSize, getCustomMenus]
  );

  const handleSearch = useCallback(
    (value: string) => {
      setSearchTerm(value);
      loadMenus(1, value);
    },
    [loadMenus]
  );

  return {
    dataList,
    loading,
    pagination,
    searchTerm,
    setSearchTerm,
    setPagination,
    loadMenus,
    handleSearch,
  };
}

interface UseCustomMenuActionsReturn {
  actionLoading: { [key: string]: boolean };
  handleToggleStatus: (record: CustomMenu) => Promise<void>;
  handleCopyMenu: (record: CustomMenu) => Promise<void>;
  handleDeleteMenu: (record: CustomMenu) => Promise<void>;
}

export function useCustomMenuActions(
  clientId: string,
  onSuccess: () => void
): UseCustomMenuActionsReturn {
  const { deleteCustomMenu, toggleCustomMenuStatus, copyCustomMenu } = useRoleApi();
  const { configMenus } = useMenus();
  const [actionLoading, setActionLoading] = useState<{ [key: string]: boolean }>({});

  const handleToggleStatus = useCallback(
    async (record: CustomMenu) => {
      const loadingKey = `toggle-${record.id}`;
      if (actionLoading[loadingKey]) return;

      setActionLoading((prev) => ({ ...prev, [loadingKey]: true }));
      try {
        await toggleCustomMenuStatus({
          id: record.id,
          is_enabled: !record.is_enabled,
        });
        message.success('Success');
        onSuccess();
      } catch (error) {
        message.error('Failed');
        console.error('Failed to toggle menu status:', error);
      } finally {
        setActionLoading((prev) => ({ ...prev, [loadingKey]: false }));
      }
    },
    [actionLoading, toggleCustomMenuStatus, onSuccess]
  );

  const handleCopyMenu = useCallback(
    async (record: CustomMenu) => {
      const loadingKey = `copy-${record.id}`;
      if (actionLoading[loadingKey]) return;

      setActionLoading((prev) => ({ ...prev, [loadingKey]: true }));
      try {
        const copyData: {
          id: number;
          app: string;
          display_name: string;
          description?: string;
          menus?: Array<{
            name: string;
            title: string;
            url?: string;
            icon?: string;
            children: Array<{ name: string; title: string; url?: string; icon?: string }>;
          }>;
        } = {
          id: record.id,
          app: clientId,
          display_name: `${record.display_name}_copy`,
          description: record.description,
        };

        if (record.is_build_in) {
          const appMenus = configMenus.filter((menu) => {
            if (!menu.url || !clientId) return false;
            const urlParts = menu.url.split('/').filter(Boolean);
            const appName = urlParts[0];
            return appName === clientId;
          });

          const menus = appMenus
            .filter((menu) => menu.url && menu.children && menu.children.length > 0)
            .map((menu) => ({
              name: menu.name,
              title: menu.title,
              url: menu.url,
              icon: menu.icon,
              children:
                menu.children?.map((child) => ({
                  name: child.name,
                  title: child.title,
                  url: child.url,
                  icon: child.icon,
                })) || [],
            }));

          copyData.menus = menus;
        }

        await copyCustomMenu(copyData);
        message.success('Success');
        onSuccess();
      } catch (error) {
        message.error('Failed');
        console.error('Failed to copy menu:', error);
      } finally {
        setActionLoading((prev) => ({ ...prev, [loadingKey]: false }));
      }
    },
    [actionLoading, clientId, configMenus, copyCustomMenu, onSuccess]
  );

  const handleDeleteMenu = useCallback(
    async (record: CustomMenu) => {
      const loadingKey = `delete-${record.id}`;
      if (actionLoading[loadingKey]) return;

      setActionLoading((prev) => ({ ...prev, [loadingKey]: true }));
      try {
        await deleteCustomMenu({ id: record.id });
        message.success('Success');
        onSuccess();
      } catch (error) {
        message.error('Failed');
        console.error('Failed to delete menu:', error);
      } finally {
        setActionLoading((prev) => ({ ...prev, [loadingKey]: false }));
      }
    },
    [actionLoading, deleteCustomMenu, onSuccess]
  );

  return {
    actionLoading,
    handleToggleStatus,
    handleCopyMenu,
    handleDeleteMenu,
  };
}

interface UseCustomMenuModalReturn {
  menuModalVisible: boolean;
  modalLoading: boolean;
  openModal: () => void;
  closeModal: () => void;
  handleAddMenuSubmit: (values: { display_name: string }) => Promise<void>;
}

export function useCustomMenuModal(
  clientId: string,
  onSuccess: () => void,
  resetForm: () => void
): UseCustomMenuModalReturn {
  const { addCustomMenu } = useRoleApi();
  const [menuModalVisible, setMenuModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);

  const openModal = useCallback(() => {
    resetForm();
    setMenuModalVisible(true);
  }, [resetForm]);

  const closeModal = useCallback(() => {
    setMenuModalVisible(false);
    resetForm();
  }, [resetForm]);

  const handleAddMenuSubmit = useCallback(
    async (values: { display_name: string }) => {
      setModalLoading(true);
      try {
        await addCustomMenu({
          display_name: values.display_name,
          app: clientId,
        });
        message.success('Success');
        resetForm();
        setMenuModalVisible(false);
        onSuccess();
      } catch (error) {
        message.error('Failed');
        console.error('Failed to add menu:', error);
      } finally {
        setModalLoading(false);
      }
    },
    [addCustomMenu, clientId, onSuccess, resetForm]
  );

  return {
    menuModalVisible,
    modalLoading,
    openModal,
    closeModal,
    handleAddMenuSubmit,
  };
}
