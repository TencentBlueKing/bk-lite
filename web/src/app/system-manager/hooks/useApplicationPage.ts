import { useState, useEffect } from 'react';
import { useScreenAwareRouter } from '@/console-layout';
import { message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { ClientData } from '@/types/index';
import { useRoleApi } from '@/app/system-manager/api/application';
import { resolveAppDescription, resolveAppDisplayName, resolveAppTag } from '@/utils/appDisplayName';

interface ApplicationClientData extends ClientData {
  source_display_name: string;
  source_description: string;
  tagList: string[];
}

export function useApplicationPage() {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const { getAll, loading, refresh } = useClientData();
  const { deleteApplication } = useRoleApi();

  const [dataList, setDataList] = useState<ApplicationClientData[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [currentItem, setCurrentItem] = useState<ApplicationClientData | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const processClientData = (data: ClientData[]): ApplicationClientData[] =>
    data
      .filter((client) => client.name !== 'ops-console')
      .map((item) => ({
        ...item,
        source_display_name: item.display_name,
        source_description: item.description,
        display_name: resolveAppDisplayName(item, t),
        description: resolveAppDescription(item, t),
        tagList: (item.tags || []).map((tag) => resolveAppTag(String(tag), t)),
        icon: item.icon || item.name,
        is_build_in: item.is_build_in,
      }));

  const refreshData = async () => {
    try {
      setRefreshing(true);
      const data = await refresh();
      if (data) setDataList(processClientData(data));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRefreshing(false);
    }
  };

  const loadItems = async (searchTerm = '') => {
    try {
      setRefreshing(true);
      const data: ClientData[] = await getAll();
      const filteredData = data.filter((item) =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setDataList(processClientData(filteredData));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const handleSearch = async (value: string) => {
    await loadItems(value);
  };

  const handleCardClick = (item: ApplicationClientData) => {
    if (item.is_build_in) {
      router.push(`/system-manager/application/manage?id=${item.id}&clientId=${item.name}`);
    } else {
      message.warning(t('system.application.builtinAppClickTip'));
    }
  };

  const handleAddNew = () => {
    setCurrentItem(null);
    setIsEdit(false);
    setModalVisible(true);
  };

  const handleEdit = (item: ApplicationClientData) => {
    setCurrentItem(item);
    setIsEdit(true);
    setModalVisible(true);
  };

  const handleDelete = (item: ApplicationClientData) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await deleteApplication({ id: item?.id });
          message.success(t('common.delSuccess'));
          await refreshData();
        } catch {
          message.error(t('common.delFailed'));
        }
      }
    });
  };

  const handleModalClose = () => setModalVisible(false);

  const handleFormSuccess = async () => {
    setModalVisible(false);
    await refreshData();
  };

  return {
    dataList,
    loading,
    refreshing,
    modalVisible,
    isEdit,
    currentItem,
    handleSearch,
    handleCardClick,
    handleAddNew,
    handleEdit,
    handleDelete,
    handleModalClose,
    handleFormSuccess
  };
}
