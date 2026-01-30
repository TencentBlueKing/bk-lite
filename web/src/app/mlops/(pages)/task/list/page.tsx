'use client'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import useMlopsTaskApi from '@/app/mlops/api/task';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Button, Input, Popconfirm, message, Tag, Tree } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import TrainTaskModal from './traintaskModal';
import TrainTaskDrawer from './traintaskDrawer';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, ColumnItem, DatasetType } from '@/app/mlops/types';
import type { Option } from '@/types';
import type { TreeDataNode } from 'antd';
import { TrainJob } from '@/app/mlops/types/task';
import { TRAIN_STATUS_MAP, TRAIN_TEXT } from '@/app/mlops/constants';
import { DataSet } from '@/app/mlops/types/manage';
const { Search } = Input;

const getStatusColor = (value: string, TrainStatus: Record<string, string>) => {
  return TrainStatus[value] || '';
};

const getStatusText = (value: string, TrainText: Record<string, string>) => {
  return TrainText[value] || '';
};

const TrainTask = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getDatasetsList } = useMlopsManageApi();
  const {
    getTrainJobList,
    deleteTrainTask,
    startTrainTask,
  } = useMlopsTaskApi();

  // 状态定义
  const modalRef = useRef<ModalRef>(null);
  const [tableData, setTableData] = useState<TrainJob[]>([]);
  const [datasetOptions, setDatasetOptions] = useState<Option[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [selectedTrain, setSelectTrain] = useState<number | null>(null);
  const [drawerOpen, setDrawOpen] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  // 抽屉操作映射
  const drawerSupportMap: Record<string, boolean> = {
    [DatasetType.ANOMALY_DETECTION]: true,
    [DatasetType.LOG_CLUSTERING]: true,
    [DatasetType.TIMESERIES_PREDICT]: true,
    [DatasetType.CLASSIFICATION]: true,
    [DatasetType.IMAGE_CLASSIFICATION]: true,
    [DatasetType.OBJECT_DETECTION]: true
  };

  // 数据处理映射
  const dataProcessorMap: Record<string, (data: any) => { tableData: TrainJob[], total: number }> = {
    [DatasetType.ANOMALY_DETECTION]: (data) => processAnomalyLikeData(data, 'anomaly'),
    [DatasetType.LOG_CLUSTERING]: (data) => processAnomalyLikeData(data, 'log_clustering'),
    [DatasetType.TIMESERIES_PREDICT]: (data) => processAnomalyLikeData(data, 'timeseries_predict'),
    [DatasetType.CLASSIFICATION]: (data) => processAnomalyLikeData(data, 'classification'),
    [DatasetType.IMAGE_CLASSIFICATION]: (data) => processAnomalyLikeData(data, 'image_classification'),
    [DatasetType.OBJECT_DETECTION]: (data) => processAnomalyLikeData(data, 'object_detection')
  };

  const treeData: TreeDataNode[] = [
    {
      title: t(`traintask.traintask`),
      key: 'traintask',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: DatasetType.ANOMALY_DETECTION,
        },
        // {
        //   title: t(`datasets.rasa`),
        //   key: DatasetType.RASA
        // },
        {
          title: t(`datasets.timeseriesPredict`),
          key: DatasetType.TIMESERIES_PREDICT,
        },
        {
          title: t(`datasets.logClustering`),
          key: DatasetType.LOG_CLUSTERING,
        },
        {
          title: t(`datasets.classification`),
          key: DatasetType.CLASSIFICATION
        },
        {
          title: t(`datasets.imageClassification`),
          key: DatasetType.IMAGE_CLASSIFICATION
        },
        {
          title: t('datasets.objectDetection'),
          key: DatasetType.OBJECT_DETECTION
        }
      ]
    }
  ];

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

  const topSection = useMemo(() => {
    return (
      <TopSection title={t('traintask.traintask')} content={t('traintask.description')} />
    );
  }, [t]);

  const leftSection = (
    <div className='w-full'>
      <Tree
        treeData={treeData}
        showLine
        selectedKeys={selectedKeys}
        defaultExpandedKeys={[DatasetType.ANOMALY_DETECTION]}
        onSelect={(keys) => setSelectedKeys(keys as string[])}
      />
    </div>
  );

  useEffect(() => {
    setSelectedKeys([DatasetType.ANOMALY_DETECTION]);
  }, []);

  useEffect(() => {
    getDatasetList();
  }, [selectedKeys])

  useEffect(() => {
    getTasks();
  }, [pagination.current, pagination.pageSize, selectedKeys]);

  const processAnomalyLikeData = (data: any, key: string) => {
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
      if (key === DatasetType.CLASSIFICATION) {
        const classjob = Object.assign(job, {
          labels: item.labels || []
        });
        return classjob
      }
      return job
    }) || [];
    return { tableData: _data, total: count || 1 };
  };

  const getTasks = async (name = '') => {
    const [activeTab] = selectedKeys;
    if (!activeTab) return;

    setLoading(true);
    try {
      const data = await fetchTaskList(name, pagination.current, pagination.pageSize);

      if (data && dataProcessorMap[activeTab]) {
        const { tableData, total } = dataProcessorMap[activeTab](data);
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
    const [activeTab] = selectedKeys;
    if (!activeTab) return;
    try {
      const data = await getDatasetsList({ key: activeTab as DatasetType });
      const items = data.map((item: DataSet) => ({
        value: item.id,
        label: item.name
      })) || [];
      setDatasetOptions(items);
    } catch (error) {
      console.error('Failed to get dataset list:', error);
    }
  };

  const fetchTaskList = useCallback(async (name: string = '', page: number = 1, pageSize: number = 10) => {
    const [activeTab] = selectedKeys;
    if (!activeTab) return { items: [], count: 0 };

    try {
      const result = await getTrainJobList({
        key: activeTab as DatasetType,
        name,
        page,
        page_size: pageSize
      });
      return result;
    } catch (error) {
      console.error(error);
      return { items: [], count: 0 };
    }
  }, [selectedKeys]);

  const openDrawer = (record: any) => {
    const [activeTab] = selectedKeys;
    if (drawerSupportMap[activeTab]) {
      setSelectTrain(record?.id);
      setDrawOpen(true);
    }
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
      const [activeTab] = selectedKeys;
      if (!activeTab) {
        message.error(t('traintask.trainNotSupported'));
        return;
      }

      await startTrainTask(record.id, activeTab as DatasetType);
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
    const [activeTab] = selectedKeys;
    if (!activeTab) {
      message.error(t('common.deleteNotSupported'));
      return;
    }

    try {
      await deleteTrainTask(record.id as string, activeTab as DatasetType);
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
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={
          (<>
            <div className="flex justify-end items-center mb-4 gap-2">
              <div className="flex items-center">
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
          </>)
        }
      />
      <TrainTaskModal ref={modalRef} onSuccess={() => onRefresh()} activeTag={selectedKeys} datasetOptions={datasetOptions} />
      <TrainTaskDrawer open={drawerOpen} onCancel={() => setDrawOpen(false)} activeTag={selectedKeys} selectId={selectedTrain} />
    </>
  );
};

export default TrainTask;