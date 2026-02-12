'use client';

import { useState, useCallback, useEffect } from 'react';
import { message, Modal } from 'antd';
import type { PaginationProps } from 'antd';
import { usePolling } from '@/hooks/usePolling';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import type { TableData } from '@/app/opspilot/types/knowledge';

interface UseDocumentTableParams {
  knowledgeBaseId: string | null;
  activeTabKey: string;
  mainTabKey: string;
  t: (key: string) => string;
  onCountsChange?: () => void;
}

interface UseDocumentTableReturn {
  tableData: TableData[];
  loading: boolean;
  pagination: PaginationProps;
  selectedRowKeys: React.Key[];
  searchText: string;
  isTrainLoading: boolean;
  singleTrainLoading: { [key: string]: boolean };
  setSelectedRowKeys: (keys: React.Key[]) => void;
  handleSearch: (value: string) => void;
  handleTableChange: (page: number, pageSize?: number) => void;
  handleDelete: (keys: React.Key[]) => void;
  handleTrain: (keys: React.Key[]) => void;
  handleBatchSet: (keys: React.Key[], params: { id: string | null; name: string | null; desc: string | null }) => string;
  fetchData: (text?: string, skipLoading?: boolean) => Promise<void>;
  rowSelection: {
    selectedRowKeys: React.Key[];
    onChange: (keys: React.Key[]) => void;
    getCheckboxProps: (record: TableData) => { disabled: boolean };
  };
}

export const useDocumentTable = ({
  knowledgeBaseId,
  activeTabKey,
  mainTabKey,
  t,
  onCountsChange,
}: UseDocumentTableParams): UseDocumentTableReturn => {
  const [searchText, setSearchText] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [isTrainLoading, setIsTrainLoading] = useState(false);
  const [singleTrainLoading, setSingleTrainLoading] = useState<{ [key: string]: boolean }>({});
  const [pagination, setPagination] = useState<PaginationProps>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const {
    fetchDocuments,
    batchDeleteDocuments,
    batchTrainDocuments,
  } = useKnowledgeApi();

  const fetchData = useCallback(async (text = '', skipLoading = false) => {
    if (!skipLoading) {
      setLoading(true);
    }
    const { current, pageSize } = pagination;
    const params = {
      name: text,
      page: current,
      page_size: pageSize,
      knowledge_source_type: activeTabKey,
      knowledge_base_id: knowledgeBaseId
    };
    try {
      const res = await fetchDocuments(params);
      const { items: data } = res;
      setTableData(data);
      setPagination(prev => ({
        ...prev,
        total: res.count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      if (!skipLoading) {
        setLoading(false);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.current, pagination.pageSize, activeTabKey, knowledgeBaseId]);

  const shouldPoll = tableData.some((item) => item.train_status === 0 || item.train_status === 4);
  usePolling(
    () => fetchData(searchText, true),
    10000,
    shouldPoll && mainTabKey === 'source_files'
  );

  useEffect(() => {
    if (mainTabKey === 'source_files') {
      fetchData(searchText);
    }
  }, [knowledgeBaseId, activeTabKey, pagination.current, pagination.pageSize, searchText]);

  const handleSearch = (value: string) => {
    setSearchText(value);
    setPagination((prev) => ({
      ...prev,
      current: 1,
    }));
  };

  const handleTableChange = (page: number, pageSize?: number) => {
    setPagination((prev) => ({
      ...prev,
      current: page,
      pageSize: pageSize || prev.pageSize,
    }));
  };

  const handleDelete = (keys: React.Key[]) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('knowledge.documents.deleteConfirmContent'),
      centered: true,
      width: 520,
      onOk: async () => {
        try {
          await batchDeleteDocuments(keys, knowledgeBaseId);
          fetchData(searchText);
          setSelectedRowKeys([]);
          onCountsChange?.();
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleConfirmTrain = async (keys: React.Key[], deleteQaPairs: boolean) => {
    if (keys.length === 1) {
      setSingleTrainLoading((prev) => ({ ...prev, [keys[0].toString()]: true }));
    } else {
      setIsTrainLoading(true);
    }
    try {
      await batchTrainDocuments(keys, deleteQaPairs);
      message.success(t('common.training'));
      fetchData(searchText);
    } catch {
      message.error(t('common.trainFailed'));
    } finally {
      if (keys.length === 1) {
        setSingleTrainLoading((prev) => ({ ...prev, [keys[0].toString()]: false }));
      } else {
        setIsTrainLoading(false);
      }
    }
  };

  const handleTrain = (keys: React.Key[]) => {
    Modal.confirm({
      title: t('knowledge.documents.trainConfirmTitle'),
      content: (
        <div className="space-y-3">
          <p>{t('knowledge.documents.trainConfirmContent')}</p>
          <div className="bg-orange-50 p-3 rounded border border-orange-200">
            <p className="text-orange-800 text-sm mb-2 font-medium">
              {t('knowledge.documents.trainWarning')}
            </p>
            <p className="text-gray-700 text-sm">
              {t('knowledge.documents.trainOptions')}
            </p>
          </div>
        </div>
      ),
      centered: true,
      width: 520,
      okText: t('knowledge.documents.keepQaPairs'),
      cancelText: t('common.cancel'),
      footer: (_, { CancelBtn }) => (
        <div className="flex justify-end gap-2">
          <CancelBtn />
          <button
            type="button"
            className="ant-btn ant-btn-default"
            onClick={() => {
              Modal.destroyAll();
              handleConfirmTrain(keys, true);
            }}
          >
            {t('knowledge.documents.deleteQaPairs')}
          </button>
          <button
            type="button"
            className="ant-btn ant-btn-primary"
            onClick={() => {
              Modal.destroyAll();
              handleConfirmTrain(keys, false);
            }}
          >
            {t('knowledge.documents.keepQaPairs')}
          </button>
        </div>
      ),
    });
  };

  const handleBatchSet = (keys: React.Key[], params: { id: string | null; name: string | null; desc: string | null }) => {
    return `/opspilot/knowledge/detail/documents/modify?type=${activeTabKey}&id=${params.id}&name=${params.name}&desc=${params.desc}&documentIds=${keys.join(',')}`;
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
    getCheckboxProps: (record: TableData) => ({
      disabled: record.train_status_display === 'Training',
    }),
  };

  return {
    tableData,
    loading,
    pagination,
    selectedRowKeys,
    searchText,
    isTrainLoading,
    singleTrainLoading,
    setSelectedRowKeys,
    handleSearch,
    handleTableChange,
    handleDelete,
    handleTrain,
    handleBatchSet,
    fetchData,
    rowSelection,
  };
};
