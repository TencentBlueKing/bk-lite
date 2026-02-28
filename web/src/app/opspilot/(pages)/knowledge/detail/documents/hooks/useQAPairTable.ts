'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { message, Modal } from 'antd';
import type { PaginationProps } from 'antd';
import { useAuth } from '@/context/auth';
import { usePolling } from '@/hooks/usePolling';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import type { QAPairData } from '@/app/opspilot/types/knowledge';

interface UseQAPairTableParams {
  knowledgeBaseId: string | null;
  mainTabKey: string;
  t: (key: string) => string;
  onCountsChange?: () => void;
}

interface UseQAPairTableReturn {
  qaPairData: QAPairData[];
  qaPairLoading: boolean;
  qaPairPagination: PaginationProps;
  selectedQAPairKeys: React.Key[];
  exportLoadingMap: { [key: number]: boolean };
  uploadModalVisible: boolean;
  confirmLoading: boolean;
  uploadedFiles: File[];
  uploadingFiles: Set<string>;
  
  setSelectedQAPairKeys: (keys: React.Key[]) => void;
  setUploadModalVisible: (visible: boolean) => void;
  handleQAPairTableChange: (page: number, pageSize?: number) => void;
  handleDeleteSingleQAPair: (qaPairId: number) => void;
  handleBatchDeleteQAPairs: () => void;
  handleExportQAPair: (qaPairId: number, qaPairName: string) => void;
  handleImportClick: () => void;
  handleUploadModalConfirm: () => Promise<void>;
  handleFileUpload: (file: File) => boolean;
  handleRemoveFile: (file: File & { uid?: string }) => void;
  handleDownloadTemplate: (fileType: 'json' | 'csv') => Promise<void>;
  fetchQAPairData: (text?: string, skipLoading?: boolean) => Promise<void>;
  qaPairRowSelection: {
    selectedRowKeys: React.Key[];
    onChange: (keys: React.Key[]) => void;
  };
}

export const useQAPairTable = ({
  knowledgeBaseId,
  mainTabKey,
  t,
  onCountsChange,
}: UseQAPairTableParams): UseQAPairTableReturn => {
  const authContext = useAuth();
  const [qaPairData, setQaPairData] = useState<QAPairData[]>([]);
  const [qaPairLoading, setQaPairLoading] = useState<boolean>(false);
  const [selectedQAPairKeys, setSelectedQAPairKeys] = useState<React.Key[]>([]);
  const [exportLoadingMap, setExportLoadingMap] = useState<{ [key: number]: boolean }>({});
  const [uploadModalVisible, setUploadModalVisible] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState<Set<string>>(new Set());
  const [searchText, setSearchText] = useState<string>('');
  const [qaPairPagination, setQaPairPagination] = useState<PaginationProps>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const uploadTimerRef = useRef<NodeJS.Timeout | null>(null);

  const { fetchQAPairs, deleteQAPair, importQaJson } = useKnowledgeApi();

  const fetchQAPairData = useCallback(async (text = '', skipLoading = false) => {
    if (!skipLoading) {
      setQaPairLoading(true);
    }
    setSearchText(text);
    const { current, pageSize } = qaPairPagination;
    const params = {
      name: text,
      page: current,
      page_size: pageSize,
      knowledge_base_id: knowledgeBaseId
    };
    try {
      const res = await fetchQAPairs(params);
      const { items: data, count } = res;
      setQaPairData(data);
      setQaPairPagination(prev => ({
        ...prev,
        total: count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      if (!skipLoading) {
        setQaPairLoading(false);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qaPairPagination.current, qaPairPagination.pageSize, knowledgeBaseId]);

  const shouldPollQAPair = qaPairData.some((item) => item.status === 'generating');
  usePolling(
    () => fetchQAPairData(searchText, true),
    10000,
    shouldPollQAPair && mainTabKey === 'qa_pairs'
  );

  useEffect(() => {
    if (mainTabKey === 'qa_pairs') {
      fetchQAPairData(searchText);
    }
  }, [mainTabKey, qaPairPagination.current, qaPairPagination.pageSize]);

  useEffect(() => {
    return () => {
      if (uploadTimerRef.current) clearTimeout(uploadTimerRef.current);
    };
  }, []);

  const handleQAPairTableChange = (page: number, pageSize?: number) => {
    setQaPairPagination((prev) => ({
      ...prev,
      current: page,
      pageSize: pageSize || prev.pageSize,
    }));
  };

  const handleDeleteSingleQAPair = async (qaPairId: number) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      onOk: async () => {
        try {
          await deleteQAPair(qaPairId);
          fetchQAPairData(searchText);
          setSelectedQAPairKeys([]);
          onCountsChange?.();
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleBatchDeleteQAPairs = async () => {
    if (selectedQAPairKeys.length === 0) {
      message.warning('Please select QA pairs to delete');
      return;
    }

    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      onOk: async () => {
        try {
          await Promise.all(selectedQAPairKeys.map(key => deleteQAPair(Number(key))));
          fetchQAPairData(searchText);
          setSelectedQAPairKeys([]);
          onCountsChange?.();
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
          setSelectedQAPairKeys([]);
        }
      },
    });
  };

  const handleExportQAPair = async (qaPairId: number, qaPairName: string) => {
    setExportLoadingMap(prev => ({ ...prev, [qaPairId]: true }));
    try {
      const response = await fetch(`/api/proxy/opspilot/knowledge_mgmt/qa_pairs/export_qa_pairs/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authContext?.token}`,
        },
        body: JSON.stringify({ qa_pairs_id: qaPairId }),
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to export QA pair');
      }
      
      const blob = await response.blob();
      const baseName = qaPairName.replace(/\.[^/.]+$/, '');
      const fileName = `${baseName}.json`;
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(fileUrl);
      message.success(t('common.successfullyExported'));
    } catch (error) {
      console.error('Error exporting QA pair:', error);
      message.error(t('common.exportFailed'));
    } finally {
      setExportLoadingMap(prev => ({ ...prev, [qaPairId]: false }));
    }
  };

  const handleImportClick = () => {
    setUploadModalVisible(true);
    setUploadedFiles([]);
    setUploadingFiles(new Set());
  };

  const handleUploadModalConfirm = async () => {
    if (uploadedFiles.length === 0) {
      message.error(t('knowledge.qaPairs.noFileSelected'));
      return;
    }

    if (uploadingFiles.size > 0) {
      message.warning(t('knowledge.qaPairs.uploadInProgress'));
      return;
    }

    try {
      setConfirmLoading(true);
      const formData = new FormData();
      formData.append('knowledge_base_id', knowledgeBaseId as string);
      uploadedFiles.forEach(file => formData.append('file', file));
      await importQaJson(formData);
      message.success(t('knowledge.qaPairs.importSuccess'));
      fetchQAPairData(searchText);
      onCountsChange?.();
    } catch {
      message.error(t('knowledge.qaPairs.importFailed'));
    } finally {
      setConfirmLoading(false);
      setUploadModalVisible(false);
      setUploadedFiles([]);
      setUploadingFiles(new Set());
    }
  };

  const handleFileUpload = (file: File) => {
    const fileId = (file as File & { uid?: string }).uid || file.name;
    
    setUploadingFiles(prev => new Set([...prev, fileId]));
    
    if (uploadTimerRef.current) clearTimeout(uploadTimerRef.current);
    uploadTimerRef.current = setTimeout(() => {
      setUploadedFiles(prev => [...prev, file]);
      setUploadingFiles(prev => {
        const newSet = new Set(prev);
        newSet.delete(fileId);
        return newSet;
      });
    }, 1000);
    
    return false;
  };

  const handleRemoveFile = (file: File & { uid?: string }) => {
    const fileId = file.uid || file.name;
    setUploadedFiles(prev => prev.filter(f => (f as File & { uid?: string }).uid !== fileId));
    setUploadingFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(fileId);
      return newSet;
    });
  };

  const handleDownloadTemplate = async (fileType: 'json' | 'csv') => {
    try {
      const response = await fetch(`/api/proxy/opspilot/knowledge_mgmt/qa_pairs/download_import_template/?file_type=${fileType}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${authContext?.token}`,
        },
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to download template');
      }
      
      const blob = await response.blob();
      const fileName = `qa_pairs_template.${fileType}`;
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(fileUrl);
      message.success(t('common.successfullyExported'));
    } catch (error) {
      console.error('Error downloading template:', error);
      message.error(t('common.exportFailed'));
    }
  };

  const qaPairRowSelection = {
    selectedRowKeys: selectedQAPairKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedQAPairKeys(newSelectedRowKeys);
    },
  };

  return {
    qaPairData,
    qaPairLoading,
    qaPairPagination,
    selectedQAPairKeys,
    exportLoadingMap,
    uploadModalVisible,
    confirmLoading,
    uploadedFiles,
    uploadingFiles,
    setSelectedQAPairKeys,
    setUploadModalVisible,
    handleQAPairTableChange,
    handleDeleteSingleQAPair,
    handleBatchDeleteQAPairs,
    handleExportQAPair,
    handleImportClick,
    handleUploadModalConfirm,
    handleFileUpload,
    handleRemoveFile,
    handleDownloadTemplate,
    fetchQAPairData,
    qaPairRowSelection,
  };
};
