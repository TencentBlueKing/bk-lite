import { useMemo, useState } from 'react';
import { useScreenAwareRouter } from '@/console-layout';
import { message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import { ClientData } from '@/types/index';
import { useRoleApi } from '@/app/system-manager/api/application';
import { resolveAppDescription, resolveAppDisplayName, resolveAppTag } from '@/utils/appDisplayName';

export interface ApplicationClientData extends ClientData {
  source_display_name: string;
  source_description: string;
  tagList: string[];
}

export function applicationListSearchText(item: ApplicationClientData): string {
  return [item.display_name, item.name].filter(Boolean).join(' ');
}

export function useApplicationPage() {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const { clientData, loading, refresh } = useClientData();
  const { deleteApplication } = useRoleApi();

  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [currentItem, setCurrentItem] = useState<ApplicationClientData | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const dataList = useMemo<ApplicationClientData[]>(
    () => clientData
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
      })),
    [clientData, t],
  );

  const refreshData = async () => {
    try {
      setRefreshing(true);
      await refresh();
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRefreshing(false);
    }
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
    handleCardClick,
    handleAddNew,
    handleEdit,
    handleDelete,
    handleModalClose,
    handleFormSuccess
  };
}
