'use client';
import { useState, useEffect, useRef } from 'react';
import { Button, Tag, message, Popconfirm, Space, Drawer } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ModalRef, ColumnItem } from '@/app/mlops/types';
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
  datasetType: 'timeseries_predict' | 'anomaly_detection' | 'classification' | 'log_clustering' | 'rasa' | 'image_classification' | 'object_detection';
}

const DatasetReleaseList: React.FC<DatasetReleaseListProps> = ({ datasetType }) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchParams = useSearchParams();
  const datasetId = searchParams.get('folder_id');
  const releaseModalRef = useRef<ModalRef>(null);

  const { getDatasetReleases, archiveDatasetRelease, unarchiveDatasetRelease, deleteDatasetRelease } = useMlopsTaskApi();

  // 判断当前类型是否支持版本管理
  const isSupportedType = datasetType === 'timeseries_predict';

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
      const result = await getDatasetReleases({
        dataset: Number(datasetId),
        page: pagination.current,
        page_size: pagination.pageSize,
      });

      setDataSource(result.items || []);
      setPagination(prev => ({
        ...prev,
        total: result.count || 0,
      }));
    } catch (error) {
      console.error('获取版本列表失败:', error);
      message.error('获取版本列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleArchive = async (record: DatasetRelease) => {
    try {
      await archiveDatasetRelease(record.id.toString());
      message.success('归档成功');
      fetchReleases();
    } catch (error) {
      console.error('归档失败:', error);
      message.error('归档失败');
    }
  };

  const handleUnarchive = async (record: DatasetRelease) => {
    try {
      await unarchiveDatasetRelease(record.id.toString());
      message.success('发布成功');
      fetchReleases()
    } catch (error) {
      console.error('发布失败', error);
      message.error('发布失败');
    }
  };

  const handleDeleteRelease = async (record: DatasetRelease) => {
    try {
      await deleteDatasetRelease(record.id.toString());
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
      published: { color: 'success', text: '已发布' },
      pending: { color: 'processing', text: '发布中' },
      failed: { color: 'error', text: '失败' },
      archived: { color: 'default', text: '归档' }
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
      title: '版本号',
      dataIndex: 'version',
      key: 'version',
      width: 120,
      render: (_, record: DatasetRelease) => <Tag color="blue">{record.version}</Tag>,
    },
    {
      title: '版本名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '文件大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 120,
      render: (_, record: DatasetRelease) => <>{formatBytes(record.file_size)}</>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (_, record: DatasetRelease) => getStatusTag(record.status),
    },
    {
      title: '创建时间',
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
          {record.status === 'archived'
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
              disabled={record.status === 'pending'}
              href={record.dataset_file}
            >
              {t(`common.download`)}
            </Button>
          }
          {record.status === 'published' && (
            <Popconfirm
              title="确认归档"
              description="归档后该版本将标记为旧版本"
              onConfirm={() => handleArchive(record)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                归档
              </Button>
            </Popconfirm>
          )}
          {record.status == 'archived' && (
            <Popconfirm
              title="确认删除"
              description="该文件将被删除"
              onConfirm={() => handleDeleteRelease(record)}
              okText="确认"
              cancelText="取消"
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
      <Button type="primary" className="mr-[10px]" onClick={handleOpenDrawer} disabled={!isSupportedType}>
        版本
      </Button>

      <Drawer
        title="数据集版本管理"
        footer={
          <div className='flex justify-end'>
            <Button type="primary" onClick={handleRelease}>
              发布版本
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
        onSuccess={() => fetchReleases()}
      />
    </>
  );
};

export default DatasetReleaseList;
