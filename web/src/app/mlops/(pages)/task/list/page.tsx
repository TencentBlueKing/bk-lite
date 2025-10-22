'use client'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import useMlopsTaskApi from '@/app/mlops/api/task';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Button, Input, Popconfirm, message, Tag, Tree } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import PermissionWrapper from '@/components/permission';
import TrainTaskModal from './traintaskModal';
import TrainTaskDrawer from './traintaskDrawer';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, ColumnItem, Option } from '@/app/mlops/types';
import type { TreeDataNode } from 'antd';
import { TrainJob } from '@/app/mlops/types/task';
import { TRAIN_STATUS_MAP, TRAIN_TEXT } from '@/app/mlops/constants';
import { DataSet } from '@/app/mlops/types/manage';
import { exportTrainFileToZip } from '@/app/mlops/utils/common';
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
  const { getAnomalyDatasetsList, getRasaDatasetsList, getLogClusteringList, getTimeSeriesPredictList, getClassificationDatasetsList } = useMlopsManageApi();
  const {
    getAnomalyTaskList,
    deleteAnomalyTrainTask,
    startAnomalyTrainTask,
    getRasaPipelines,
    deleteRasaPipelines,
    getLogClusteringTaskList,
    deleteLogClusteringTrainTask,
    startLogClusteringTrainTask,
    getTimeSeriesTaskList,
    deleteTimeSeriesTrainTask,
    startTimeSeriesTrainTask,
    getClassificationTaskList,
    deleteClassificationTrainTask,
    startClassificationTrainTask,
    getTrainTaskFile
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
  const showTrain = ['anomaly', 'classification'];

  // 数据集获取映射
  const datasetApiMap: Record<string, () => Promise<DataSet[]>> = {
    'anomaly': () => getAnomalyDatasetsList({}),
    'rasa': () => getRasaDatasetsList({}),
    'log_clustering': () => getLogClusteringList({}),
    'timeseries_predict': () => getTimeSeriesPredictList({}),
    'classification': () => getClassificationDatasetsList({})
  };

  // 任务获取映射
  const taskApiMap: Record<string, (params: any) => Promise<any>> = {
    'anomaly': (params) => getAnomalyTaskList(params),
    'rasa': () => getRasaPipelines({}),
    'log_clustering': (params) => getLogClusteringTaskList(params),
    'timeseries_predict': (params) => getTimeSeriesTaskList(params),
    'classification': (params) => getClassificationTaskList(params)
  };

  // 训练开始操作映射
  const trainStartApiMap: Record<string, (id: any) => Promise<void>> = {
    'anomaly': startAnomalyTrainTask,
    'log_clustering': startLogClusteringTrainTask,
    'timeseries_predict': startTimeSeriesTrainTask,
    'classification': startClassificationTrainTask
  };

  // 删除操作映射
  const deleteApiMap: Record<string, (id: string) => Promise<void>> = {
    'anomaly': deleteAnomalyTrainTask,
    'rasa': deleteRasaPipelines,
    'log_clustering': deleteLogClusteringTrainTask,
    'timeseries_predict': deleteTimeSeriesTrainTask,
    'classification': deleteClassificationTrainTask
  };

  // 抽屉操作映射
  const drawerSupportMap: Record<string, boolean> = {
    'anomaly': true,
    'rasa': false,
    'log_clustering': false,
    'timeseries_predict': false,
    'classification': true
  };

  // 数据处理映射
  const dataProcessorMap: Record<string, (data: any) => { tableData: TrainJob[], total: number }> = {
    'anomaly': (data) => processAnomalyLikeData(data, 'anomaly'),
    'rasa': (data) => {
      const _data = data.map((item: any) => ({
        id: item.id,
        name: item.name,
        dataset_count: item?.dataset_count,
        dataset_nameas: item?.dataset_names,
        datasets: item.datasets,
        creator: item?.created_by,
        created_at: item?.created_at,
        config: item?.config,
        datasets_detail: item?.datasets_detail
      }));
      return { tableData: _data, total: data?.length || 0 };
    },
    'log_clustering': (data) => processAnomalyLikeData(data, 'log_clustering'),
    'timeseries_predict': (data) => processAnomalyLikeData(data, 'timeseries_predict'),
    'classification': (data) => processAnomalyLikeData(data, 'classification')
  };

  const treeData: TreeDataNode[] = [
    {
      title: t(`traintask.traintask`),
      key: 'traintask',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: 'anomaly',
        },
        {
          title: t(`datasets.rasa`),
          key: 'rasa'
        },
        {
          title: t(`datasets.timeseriesPredict`),
          key: 'timeseries_predict',
        },
        {
          title: t(`datasets.logClustering`),
          key: 'log_clustering',
        },
        {
          title: t(`datasets.classification`),
          key: 'classification'
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
              className="block w-[18px] h-[18px] leading-[18px] text-center content-center rounded-[50%] mr-2 text-white"
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
          {t(`traintask.${getStatusText(record.status, TRAIN_TEXT)}`)}
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
        const [key] = selectedKeys;
        return (
          <>
            <PermissionWrapper requiredPermissions={['View']}>
              <Button
                type="link"
                className="mr-[10px]"
                onClick={() => downloadFile(record)}
              >
                {t('common.download')}
              </Button>
            </PermissionWrapper>
            {showTrain.includes(key) &&
              (<>
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
                      className="mr-[10px]"
                    >
                      {t('traintask.train')}
                    </Button>
                  </Popconfirm>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['View']}>
                  <Button
                    type="link"
                    className="mr-[10px]"
                    onClick={() => openDrawer(record)}
                  >
                    {t('common.detail')}
                  </Button>
                </PermissionWrapper>
              </>)
            }
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                className="mr-[10px]"
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
                <Button type="link" danger>{t('common.delete')}</Button>
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
        defaultExpandedKeys={['anomaly']}
        onSelect={(keys) => setSelectedKeys(keys as string[])}
      />
    </div>
  );

  useEffect(() => {
    setSelectedKeys(['anomaly']);
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
        train_data_id: item.train_data_id,
        val_data_id: item.val_data_id,
        test_data_id: item.test_data_id,
        created_at: item.created_at,
        creator: item?.created_by,
        status: item?.status,
        max_evals: item.max_evals,
        algorithm: item.algorithm,
        hyperopt_config: item.hyperopt_config
      }
      if (key === 'classification') {
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
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const getDatasetList = async () => {
    const [activeTab] = selectedKeys;
    if (!activeTab || !datasetApiMap[activeTab]) return;

    try {
      const data = await datasetApiMap[activeTab]();
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
    if (!activeTab || !taskApiMap[activeTab]) return { items: [], count: 0 };

    try {
      if (activeTab === 'rasa') {
        // RASA 特殊处理，不需要分页参数
        return await taskApiMap[activeTab]({});
      } else {
        // 其他类型需要分页参数
        const result = await taskApiMap[activeTab]({
          name,
          page,
          page_size: pageSize
        });
        return result;
      }
    } catch (error) {
      console.error(error);
      return { items: [], count: 0 };
    }
  }, [selectedKeys, taskApiMap]);

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
      if (!activeTab || !trainStartApiMap[activeTab]) {
        message.error(t('traintask.trainNotSupported'));
        return;
      }

      await trainStartApiMap[activeTab](record.id);
      message.success(t(`traintask.trainStartSucess`));
    } catch (e) {
      console.log(e);
      message.error(t(`common.error`));
    } finally {
      getTasks();
    }
  };

  const downloadFile = async (record: any) => {
    const [key] = selectedKeys;
    try {
      const zipname = `${record.name}_${record.id}`;
      message.info(t(`traintask.waitData`))
      const data = await getTrainTaskFile(record.id, key);
      message.success(t(`traintask.downloadStart`));
      exportTrainFileToZip(data, zipname);
    } catch (e) {
      console.log(e);
      message.error(t(`traintask.downloadFailed`));
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
    if (!activeTab || !deleteApiMap[activeTab]) {
      message.error(t('common.deleteNotSupported'));
      return;
    }

    try {
      await deleteApiMap[activeTab](record.id as string);
      message.success(t('common.delSuccess'));
    } catch (e) {
      console.log(e);
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
              <div className="flex">
                <Search
                  className="w-[240px] mr-1.5"
                  placeholder={t('traintask.searchText')}
                  enterButton
                  onSearch={onSearch}
                  style={{ fontSize: 15 }}
                />
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} className="rounded-md text-xs shadow mr-2" onClick={() => handleAdd()}>
                    {t('common.add')}
                  </Button>
                </PermissionWrapper>
                <ReloadOutlined onClick={onRefresh} />
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