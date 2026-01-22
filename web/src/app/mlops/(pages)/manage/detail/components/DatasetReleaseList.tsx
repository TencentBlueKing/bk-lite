'use client';
import { useState, useEffect, useRef } from 'react';
import { Button, Tag, message, Popconfirm, Space, Drawer } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ModalRef, ColumnItem, DatasetReleaseKey } from '@/app/mlops/types';
import DatasetReleaseModal from './DatasetReleaseModal';

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
  datasetType: DatasetReleaseKey;
}

const SUPPORTED_DATASET_TYPES = ['timeseries_predict', 'anomaly_detection', 'log_clustering', 'classification', 'image_classification', 'object_detection'];

const DatasetReleaseList: React.FC<DatasetReleaseListProps> = ({ datasetType }) => {
  const { t } = useTranslation();
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
      console.log(datasetId, datasetType, pagination.current)
      fetchReleases();
    }
  }, [datasetId, datasetType, pagination.current]);

  const fetchReleases = async () => {
    if (!isSupportedType) return;
    setLoading(true);
    try {
      console.log(datasetType)
      const result = await taskApi.getDatasetReleases(
        datasetType as 'timeseries_predict' | 'anomaly_detection',
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
        datasetType as 'timeseries_predict' | 'anomaly_detection',
        record.id.toString()
      );
      message.success(t(`common.delSuccess`));
      fetchReleases();
    } catch (e) {
      console.log(e);
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

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      published: { color: 'success', text: t(`mlops-common.published`) },
      pending: { color: 'processing', text: t(`mlops-common.publishing`) },
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
              disabled={record.status === 'pending' || record.status == 'failed'}
              href={record.dataset_file}
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
          {(record.status == 'archived' || record.status == 'failed') && (
            <Popconfirm
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
