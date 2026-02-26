'use client'
import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import useMlopsTaskApi from '@/app/mlops/api/task';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Button, Input, Popconfirm, message, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import TrainTaskModal from '@/app/mlops/components/TrainTaskModal';
import TrainTaskDrawer from '@/app/mlops/components/TrainTaskDrawer';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, ColumnItem, DatasetType } from '@/app/mlops/types';
import type { Option } from '@/types';
import { TrainJob } from '@/app/mlops/types/task';
import { TRAIN_STATUS_MAP, TRAIN_TEXT, ALGORITHM_TYPE_I18N_KEYS } from '@/app/mlops/constants';
import { DataSet } from '@/app/mlops/types/manage';
const { Search } = Input;

const getStatusColor = (value: string, TrainStatus: Record<string, string>) => {
  return TrainStatus[value] || '';
};

const getStatusText = (value: string, TrainText: Record<string, string>) => {
  return TrainText[value] || '';
};

const TrainingPage = () => {
  const { t } = useTranslation();
  const params = useParams();
  const algorithmType = params.algorithmType as DatasetType;

  const { convertToLocalizedTime } = useLocalizedTime();
  const { getDatasetsList } = useMlopsManageApi();
  const {
    getTrainJobList,
    deleteTrainTask,
    startTrainTask,
  } = useMlopsTaskApi();

  const modalRef = useRef<ModalRef>(null);
  const [tableData, setTableData] = useState<TrainJob[]>([]);
  const [datasetOptions, setDatasetOptions] = useState<Option[]>([]);
  const [selectedTrain, setSelectTrain] = useState<number | null>(null);
  const [drawerOpen, setDrawOpen] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      key: 'name',
      dataIndex: 'name',
    },
    {
      title: t('mlops-common.createdAt'),
      key: 'created_at',
      dataIndex: 'created_at',
      render: (_, record) => {
        return (<p>{convertToLocalizedTime(record.created_at, 'YYYY-MM-DD HH:mm:ss')}</p>)
      }
    },
    {
      title: t('mlops-common.creator'),
      key: 'creator',
      dataIndex: 'creator',
      width: 120,
      render: (_, { creator }) => {
        return creator ? (
          <div className="flex h-full items-center" title={creator}>
            <span
              className="block w-4.5 h-4.5 leading-4.5 text-center content-center rounded-[50%] mr-2 text-white"
              style={{ background: 'blue' }}
            >
              {creator.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span>
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={creator}
              />
            </span>
          </div>
        ) : (
          <>--</>
        );
      }
    },
    {
      title: t('mlops-common.status'),
      key: 'status',
      dataIndex: 'status',
      width: 120,
      render: (_, record: TrainJob) => {
        return record.status ? (<Tag color={getStatusColor(record.status, TRAIN_STATUS_MAP)} className=''>
          {t(`mlops-common.${getStatusText(record.status, TRAIN_TEXT)}`)}
        </Tag>) : (<p>--</p>)
      }
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 240,
      fixed: 'right',
      align: 'center',
      render: (_: unknown, record: TrainJob) => {
        return (
          <>
            <PermissionWrapper requiredPermissions={['Train']}>
              <Popconfirm
                title={t('traintask.trainStartTitle')}
                description={t('traintask.trainStartContent')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => onTrainStart(record)}
              >
                <Button
                  type="link"
                  className="mr-2.5"
                  disabled={record.status === 'running'}
                >
                  {t('traintask.train')}
                </Button>
              </Popconfirm>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['View']}>
              <Button
                type="link"
                className="mr-2.5"
                onClick={() => openDrawer(record)}
              >
                {t('common.detail')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                className="mr-2.5"
                disabled={record.status === 'running'}
                onClick={() => handleEdit(record)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Popconfirm
                title={t('traintask.delTraintask')}
                description={t(`traintask.delTraintaskContent`)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => onDelete(record)}
              >
                <Button type="link" danger disabled={record.status === 'running'}>{t('common.delete')}</Button>
              </Popconfirm>
            </PermissionWrapper>
          </>
        )
      },
    },
  ];

  useEffect(() => {
    getDatasetList();
  }, [algorithmType]);

  useEffect(() => {
    getTasks();
  }, [pagination.current, pagination.pageSize, algorithmType]);

  const processData = (data: any) => {
    const { items, count } = data;
    const _data = items?.map((item: any) => {
      const job = {
        id: item.id,
        name: item.name,
        dataset_version: item.dataset_version,
        created_at: item.created_at,
        creator: item?.created_by,
        status: item?.status,
        max_evals: item.max_evals,
        algorithm: item.algorithm,
        hyperopt_config: item.hyperopt_config
      }
      if (algorithmType === DatasetType.CLASSIFICATION) {
        return Object.assign(job, { labels: item.labels || [] });
      }
      return job
    }) || [];
    return { tableData: _data, total: count || 1 };
  };

  const getTasks = async (name = '') => {
    if (!algorithmType) return;

    setLoading(true);
    try {
      const data = await getTrainJobList({
        key: algorithmType,
        name,
        page: pagination.current,
        page_size: pagination.pageSize
      });

      if (data) {
        const { tableData, total } = processData(data);
        setTableData(tableData as TrainJob[]);
        setPagination(prev => ({
          ...prev,
          total: total,
        }));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getDatasetList = async () => {
    if (!algorithmType) return;
    try {
      const data = await getDatasetsList({ key: algorithmType });
      const items = data.map((item: DataSet) => ({
        value: item.id,
        label: item.name
      })) || [];
      setDatasetOptions(items);
    } catch (error) {
      console.error('Failed to get dataset list:', error);
    }
  };

  const openDrawer = (record: any) => {
    setSelectTrain(record?.id);
    setDrawOpen(true);
  };

  const handleAdd = () => {
    if (modalRef.current) {
      modalRef.current.showModal({
        type: 'add',
        title: 'addtask',
        form: {}
      })
    }
  };

  const handleEdit = (record: TrainJob) => {
    if (modalRef.current) {
      modalRef.current.showModal({
        type: 'update',
        title: 'edittask',
        form: record
      })
    }
  };

  const onTrainStart = async (record: TrainJob) => {
    try {
      await startTrainTask(record.id, algorithmType);
      message.success(t(`traintask.trainStartSucess`));
    } catch (e) {
      console.error(e);
      message.error(t(`common.error`));
    } finally {
      getTasks();
    }
  };

  const handleChange = (value: any) => {
    setPagination(value);
  };

  const onSearch = (value: string) => {
    getTasks(value);
  };

  const onDelete = async (record: TrainJob) => {
    try {
      await deleteTrainTask(record.id as string, algorithmType);
      message.success(t('common.delSuccess'));
    } catch (e) {
      console.error(e);
      message.error(t('common.delFailed'));
    } finally {
      getTasks();
    }
  };

  const onRefresh = () => {
    getTasks();
    getDatasetList();
  };

  return (
    <>
      <div className="flex justify-between items-center mb-4 gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Tag color="blue" className="shrink-0">
            {t(ALGORITHM_TYPE_I18N_KEYS[algorithmType] || algorithmType)}
          </Tag>
          {/* <span className="text-gray-500 text-sm truncate">
            {t('traintask.pageDescription')}
          </span> */}
          <EllipsisWithTooltip className="w-full overflow-hidden text-ellipsis whitespace-nowrap" text={t('traintask.pageDescription')} />
        </div>
        <div className="flex items-center shrink-0">
          <Search
            className="w-60 mr-1.5"
            placeholder={t('traintask.searchText')}
            enterButton
            onSearch={onSearch}
            style={{ fontSize: 15 }}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" className="rounded-md text-xs shadow mr-2" onClick={() => handleAdd()}>
              {t('common.add')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['View']}>
            <ReloadOutlined onClick={onRefresh} />
          </PermissionWrapper>
        </div>
      </div>
      <div className="flex-1 relative">
        <div className='absolute w-full'>
          <CustomTable
            rowKey="id"
            className="mt-3"
            scroll={{ x: '100%', y: 'calc(100vh - 410px)' }}
            dataSource={tableData}
            columns={columns}
            pagination={pagination}
            loading={loading}
            onChange={handleChange}
          />
        </div>
      </div>
      <TrainTaskModal ref={modalRef} onSuccess={() => onRefresh()} activeTag={[algorithmType]} datasetOptions={datasetOptions} />
      <TrainTaskDrawer open={drawerOpen} onCancel={() => setDrawOpen(false)} activeTag={[algorithmType]} selectId={selectedTrain} />
    </>
  );
};

export default TrainingPage;
