import { useState, useRef, useCallback, useEffect } from 'react';
import { message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

interface UseSettingsTableOptions<T> {
  fetchList: (params: { page: number; page_size: number; name?: string }) => Promise<{ items: T[]; count: number }>;
  deleteItem: (id: number) => Promise<void>;
  patchItem?: (id: number, data: { is_active: boolean }) => Promise<unknown>;
}

interface UseSettingsTableReturn<T> {
  tableLoading: boolean;
  loadingIds: Record<number, boolean>;
  operateVisible: boolean;
  setOperateVisible: (visible: boolean) => void;
  searchKey: string;
  setSearchKey: (key: string) => void;
  dataList: T[];
  currentRow: T | null;
  pagination: Pagination;
  handleEdit: (type: 'add' | 'edit', row?: T) => void;
  handleDelete: (row: T & { id: number }) => void;
  handleFilterChange: () => void;
  handleFilterClear: () => void;
  handleTableChange: (newPagination: Pagination) => void;
  handleStatusToggle: (row: T & { id: number }, checked: boolean) => void;
  refreshList: (params?: { current?: number; pageSize?: number }) => void;
}

export function useSettingsTable<T>({
  fetchList,
  deleteItem,
  patchItem,
}: UseSettingsTableOptions<T>): UseSettingsTableReturn<T> {
  const { t } = useTranslation();
  const listCount = useRef<number>(0);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [loadingIds, setLoadingIds] = useState<Record<number, boolean>>({});
  const [operateVisible, setOperateVisible] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');
  const [dataList, setDataList] = useState<T[]>([]);
  const [currentRow, setCurrentRow] = useState<T | null>(null);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const getTableList = useCallback(async (params: { current?: number; pageSize?: number; searchKey?: string } = {}) => {
    try {
      setTableLoading(true);
      const searchVal = params.searchKey !== undefined ? params.searchKey : searchKey;
      const queryParams = {
        page: params.current || pagination.current,
        page_size: params.pageSize || pagination.pageSize,
        name: searchVal || undefined,
      };
      const data = await fetchList(queryParams);
      setDataList(data.items || []);
      listCount.current = data.items?.length || 0;
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch {
      message.error(t('common.loadFailed'));
    } finally {
      setTableLoading(false);
    }
  }, [fetchList, pagination.current, pagination.pageSize, searchKey, t]);

  useEffect(() => {
    getTableList();
  }, []);

  const handleEdit = useCallback((type: 'add' | 'edit', row?: T) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(null);
    }
    setOperateVisible(true);
  }, []);

  const handleDelete = useCallback((row: T & { id: number }) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await deleteItem(row.id);
          message.success(t('successfullyDeleted'));
          if (pagination.current > 1 && listCount.current === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            getTableList({
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            getTableList();
          }
        } catch {
          message.error(t('alarmCommon.operateFailed'));
        }
      },
    });
  }, [deleteItem, getTableList, pagination.current, pagination.pageSize, t]);

  const handleFilterChange = useCallback(() => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({ current: 1 });
  }, [getTableList]);

  const handleFilterClear = useCallback(() => {
    setSearchKey('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({ current: 1, searchKey: '' });
  }, [getTableList]);

  const handleTableChange = useCallback((newPagination: Pagination) => {
    setPagination(newPagination);
    getTableList({ current: newPagination.current, pageSize: newPagination.pageSize });
  }, [getTableList]);

  const handleStatusToggle = useCallback(async (row: T & { id: number }, checked: boolean) => {
    if (!patchItem) return;
    
    setLoadingIds((ids) => ({ ...ids, [row.id]: true }));
    try {
      const data = await patchItem(row.id, { is_active: checked });
      if (!data) {
        message.error(t('alarmCommon.operateFailed'));
      } else {
        message.success(
          checked ? t('settings.enableSuccess') : t('settings.disableSuccess')
        );
      }
      getTableList();
    } catch {
      console.error(t('alarmCommon.operateFailed'));
    } finally {
      setLoadingIds((ids) => {
        const nxt = { ...ids };
        delete nxt[row.id];
        return nxt;
      });
    }
  }, [patchItem, getTableList, t]);

  const refreshList = useCallback((params?: { current?: number; pageSize?: number }) => {
    if (params?.current === 1) {
      setPagination((prev) => ({ ...prev, current: 1 }));
    }
    getTableList(params || {});
  }, [getTableList]);

  return {
    tableLoading,
    loadingIds,
    operateVisible,
    setOperateVisible,
    searchKey,
    setSearchKey,
    dataList,
    currentRow,
    pagination,
    handleEdit,
    handleDelete,
    handleFilterChange,
    handleFilterClear,
    handleTableChange,
    handleStatusToggle,
    refreshList,
  };
}
