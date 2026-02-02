'use client';
import { useState, useEffect, useRef } from 'react';
import { Button, Tag, message, Popconfirm, Space, Drawer } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ModalRef, ColumnItem, DatasetType } from '@/app/mlops/types';
import { DATASET_RELEASE_MAP } from '@/app/mlops/constants';
import DatasetReleaseModal from './DatasetReleaseModal';
import { useAuth } from "@/context/auth";

interface DatasetRelease {
  id: number;
  name: string;
  version: string;
  description: string;
  dataset_file: string;
  file_size: number;
  status: string;
  created_at: string;
  metadata: {
    train_samples: number;
    val_samples: number;
    test_samples: number;
    total_samples: number;
    source?: {
      train_job_name?: string;
    };
  };
}

interface DatasetReleaseListProps {
  datasetType: DatasetType;
}

const SUPPORTED_DATASET_TYPES = [
  DatasetType.TIMESERIES_PREDICT,
  DatasetType.ANOMALY_DETECTION,
  DatasetType.LOG_CLUSTERING,
  DatasetType.CLASSIFICATION,
  DatasetType.IMAGE_CLASSIFICATION,
  DatasetType.OBJECT_DETECTION
];

const DatasetReleaseList: React.FC<DatasetReleaseListProps> = ({ datasetType }) => {
  const { t } = useTranslation();
  const authContext = useAuth();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchParams = useSearchParams();
  const datasetId = searchParams.get('folder_id');
  const releaseModalRef = useRef<ModalRef>(null);

  const taskApi = useMlopsTaskApi();

  // 判断当前类型是否支持版本管理
  const isSupportedType = SUPPORTED_DATASET_TYPES.includes(datasetType);

  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<DatasetRelease[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  useEffect(() => {
    if (datasetId && isSupportedType && open) {
      fetchReleases();
    }
  }, [datasetId, datasetType, pagination.current]);

  const fetchReleases = async () => {
    if (!isSupportedType) return;
    setLoading(true);
    try {
      const result = await taskApi.getDatasetReleases(
        datasetType,
        {
          dataset: Number(datasetId),
          page: pagination.current,
          page_size: pagination.pageSize,
        }
      );

      setDataSource(result.items || []);
      setPagination(prev => ({
        ...prev,
        total: result.count || 0,
      }));
    } catch (error) {
      console.error(t(`common.fetchFailed`), error);
      message.error(t(`common.fetchFailed`));
    } finally {
      setLoading(false);
    }
  };

  const handleArchive = async (record: DatasetRelease) => {
    try {
      await taskApi.archiveDatasetRelease(
        datasetType,
        record.id.toString()
      );
      message.success(t(`common.updateSuccess`));
      fetchReleases();
    } catch (error) {
      console.error(t(`common.updateFailed`), error);
      message.error(t(`common.updateFailed`));
    }
  };

  const handleUnarchive = async (record: DatasetRelease) => {
    try {
      await taskApi.unarchiveDatasetRelease(
        datasetType,
        record.id.toString()
      );
      message.success(t(`common.publishSuccess`));
      fetchReleases()
    } catch (error) {
      console.error(t(`mlops-common.publishFailed`), error);
      message.error(t(`mlops-common.publishFailed`));
    }
  };

  const handleDeleteRelease = async (record: DatasetRelease) => {
    try {
      await taskApi.deleteDatasetRelease(
        datasetType,
        record.id.toString()
      );
      message.success(t(`common.delSuccess`));
      fetchReleases();
    } catch (e) {
      console.error(e);
      message.error(t(`common.delFailed`));
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleOpenDrawer = () => {
    setOpen(true);
    if (isSupportedType) {
      fetchReleases();
    }
  };

  const handleCloseDrawer = () => {
    setOpen(false);
  };

  const handleRelease = () => {
    releaseModalRef.current?.showModal({ type: '' });
  };

  const downloadReleaseZip = async (record: any) => {
    try {
      message.info(t(`mlops-common.downloadStart`));

      const response = await fetch(
        `/api/proxy/mlops/${DATASET_RELEASE_MAP[datasetType]}/${record.id}/download/`,
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${authContext?.token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`${t('mlops-common.downloadFailed')}: ${response.status}`);
      }

      const blob = await response.blob();

      // 从 Content-Disposition 头提取文件名
      const contentDisposition = response.headers.get('content-disposition');
      let fileName = `${record.name}.zip`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename[^;=\n]*=(['\"]?)([^'"\n]*?)\1/);
        if (match && match[2]) {
          fileName = match[2];
        }
      }

      // 创建下载链接
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(fileUrl);
    } catch (error: any) {
      console.error(t(`mlops-common.downloadFailed`), error);
      message.error(error.message || t('common.errorFetch'));
    }
  };

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      published: { color: 'success', text: t(`mlops-common.published`) },
      pending: { color: 'default', text: t(`mlops-common.pending`) },
      processing: { color: 'processing', text: t(`mlops-common.publishing`) },
      failed: { color: 'error', text: t(`mlops-common.failed`) },
      archived: { color: 'default', text: t(`mlops-common.archived`) }
    };
    const config = statusMap[status] || { color: 'default', text: status };
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const handleTableChange = (value: any) => {
    setPagination(prev => ({
      ...prev,
      current: value.current,
      pageSize: value.pageSize
    }));
  };

  const columns: ColumnItem[] = [
    {
      title: t(`common.version`),
      dataIndex: 'version',
      key: 'version',
      width: 120,
      render: (_, record: DatasetRelease) => <Tag color="blue">{record.version}</Tag>,
    },
    {
      title: t(`common.name`),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: t(`datasets.fileSize`),
      dataIndex: 'file_size',
      key: 'file_size',
      width: 120,
      render: (_, record: DatasetRelease) => <>{formatBytes(record.file_size)}</>,
    },
    {
      title: t(`mlops-common.status`),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (_, record: DatasetRelease) => getStatusTag(record.status),
    },
    {
      title: t(`mlops-common.createdAt`),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (_, record: DatasetRelease) => <>{convertToLocalizedTime(record.created_at, 'YYYY-MM-DD HH:mm:ss')}</>,
    },
    {
      title: t(`common.action`),
      key: 'action',
      dataIndex: 'action',
      width: 100,
      fixed: 'right' as const,
      // align: 'center',
      render: (_: any, record: DatasetRelease) => (
        <Space size="small">
          {(record.status === 'archived')
            ? <Button
              type='link'
              size='small'
              onClick={() => handleUnarchive(record)}
            >
              {t(`common.publish`)}
            </Button>
            : <Button
              type="link"
              size="small"
              disabled={['pending', 'processing', 'failed'].includes(record.status)}
              onClick={() => downloadReleaseZip(record)}
            >
              {t(`common.download`)}
            </Button>
          }
          {record.status === 'published' && (
            <Popconfirm
              title={t(`mlops-common.archiveConfirm`)}
              description={t(`mlops-common.archivingMsg`)}
              onConfirm={() => handleArchive(record)}
              okText={t(`common.confirm`)}
              cancelText={t(`common.cancel`)}
            >
              <Button type="link" size="small" danger>
                {t(`mlops-common.archived`)}
              </Button>
            </Popconfirm>
          )}
          {['archived', 'failed', 'pending', 'processing'].includes(record.status) && (
            <Popconfirm
              placement='left'
              title={t(`mlops-common.deleteConfirm`)}
              description={t(`mlops-common.fileDelDes`)}
              onConfirm={() => handleDeleteRelease(record)}
              okText={t(`common.confirm`)}
              cancelText={t(`common.cancel`)}
            >
              <Button type="link" size="small" danger>
                {t(`common.delete`)}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Button type="primary" className="mr-2.5" onClick={handleOpenDrawer} disabled={!isSupportedType}>
        {t(`common.version`)}
      </Button>

      <Drawer
        title={t(`datasets.datasetsRelease`)}
        footer={
          <div className='flex justify-end'>
            <Button type="primary" onClick={handleRelease}>
              {t(`common.publish`)}
            </Button>
          </div>
        }
        placement="right"
        width={850}
        onClose={handleCloseDrawer}
        open={open}
      >
        <CustomTable
          rowKey="id"
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ x: '100%', y: 'calc(100vh - 265px)' }}
        />
      </Drawer>

      <DatasetReleaseModal
        ref={releaseModalRef}
        datasetId={datasetId || ''}
        datasetType={datasetType}
        onSuccess={() => fetchReleases()}
      />
    </>
  );
};

export default DatasetReleaseList;
