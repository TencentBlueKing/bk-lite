'use client';
import { useState, useRef, useEffect, useMemo } from "react";
import useMlopsTaskApi from "@/app/mlops/api/task";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { Button, Popconfirm, message, Tree, type TreeDataNode, Tag, Tooltip } from "antd";
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import PageLayout from '@/components/page-layout';
import TopSection from "@/components/top-section";
import ReleaseModal from "./releaseModal";
import PermissionWrapper from '@/components/permission';
import { ModalRef, Option, Pagination, TableData } from "@/app/mlops/types";
import { ColumnItem } from "@/types";
import { TrainJob } from "@/app/mlops/types/task";

const CONTAINER_STATE_MAP: Record<string, string> = {
  'running': 'green',
  'completed': 'blue',
  'not_found': 'default',
  'unknown': 'orange',
  'error': 'red'
};

const CONTAINER_TEXT_MAP: Record<string, string> = {
  'running': '运行中',
  'completed': '已完成',
  'not_found': '容器不存在',
  'unknown': '状态异常',
  'error': '错误'
};

// running: 正在提供服务的容器
// completed: 训练任务正常完成
// failed: 训练任务异常退出，需要查看日志
// not_found: 容器已被删除或从未创建
// unknown: 容器处于未知状态（罕见，可能是 Docker 问题）


const ModelRelease = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const { getAnomalyTaskList, getLogClusteringTaskList, getTimeSeriesTaskList, getClassificationTaskList } = useMlopsTaskApi();
  const {
    getAnomalyServingsList, deleteAnomalyServing, updateAnomalyServings,
    getTimeSeriesPredictServingsList, deleteTimeSeriesPredictServing, updateTimeSeriesPredictServings,
    getLogClusteringServingsList, deleteLogClusteringServing, updateLogClusteringServings,
    getClassificationServingsList, deleteClassificationServing, updateClassificationServings,
    stopTimeseriesPredictServingContainer,
    startTimeseriesPredictServingContainer,
  } = useMlopsModelReleaseApi();
  const [trainjobs, setTrainjobs] = useState<Option[]>([]);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  const treeData: TreeDataNode[] = [
    {
      title: t(`model-release.title`),
      key: 'modelRelease',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: 'anomaly_detection',
        },
        // {
        //   title: t(`datasets.rasa`),
        //   key: 'rasa'
        // },
        {
          title: t(`datasets.timeseriesPredict`),
          key: 'timeseries_predict'
        },
        {
          title: t(`datasets.logClustering`),
          key: 'log_clustering'
        },
        {
          title: t(`datasets.classification`),
          key: 'classification'
        },
        {
          title: t(`datasets.imageClassification`),
          key: 'image_classification'
        },
        {
          title: t(`datasets.objectDetection`),
          key: 'object_detection'
        }
      ]
    }
  ];

  const columns: ColumnItem[] = [
    {
      title: t(`model-release.modelName`),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t(`model-release.modelDescription`),
      dataIndex: 'description',
      key: 'description'
    },
    {
      title: t(`model-release.publishStatus`),
      dataIndex: 'status',
      key: 'status',
      render: (_, record) => {
        const isAcitve = record.status === 'active'
        // return <Switch checked={record.status === 'active'} onChange={(value: boolean) => handleModelAcitve(record.id, value)} />
        return <Tag color={isAcitve ? 'green' : 'default'}>{isAcitve ? '已发布' : '未发布'}</Tag>
      }
    },
    {
      title: '容器状态',
      dataIndex: 'container_info',
      key: 'container_info',
      render: (_, record) => {
        const { status, state, detail } = record.container_info;
        const isSucess = status === 'success';
        const _status = isSucess ? state : status;
        const text = isSucess ? state : 'error';
        return (<>
          <Tooltip title={detail || ''}>
            <Tag color={CONTAINER_STATE_MAP[_status]}>{CONTAINER_TEXT_MAP[text]}</Tag>
          </Tooltip>
        </>)
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (_, record: TableData) => {
        const { status } = record;
        const { state } = record.container_info;
        const isActive = record.status === 'active';
        return (<>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`model-release.configuration`)}</Button>
          </PermissionWrapper>
          {status !== 'active' ?
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" onClick={() => handleModelAcitve(record.id, isActive)}>{t(`model-release.release`)}</Button>
            </PermissionWrapper> :
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" danger onClick={() => handleModelAcitve(record.id, isActive)}>{t(`model-release.discontinued`)}</Button>
            </PermissionWrapper>
          }
          {state !== 'running' ?
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" onClick={() => handleStartContainer(record.id)}>{t(`mlops-common.start`)}</Button>
            </PermissionWrapper> :
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" danger onClick={() => handleStopContainer(record.id)}>{t(`mlops-common.stop`)}</Button>
            </PermissionWrapper>
          }
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t(`model-release.delModel`)}
              description={t(`model-release.delModelContent`)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger disabled={state === 'running'}>{t(`common.delete`)}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>)
      }
    }
  ];

  const getServingsMap: Record<string, any> = {
    'anomaly_detection': getAnomalyServingsList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringServingsList,
    'timeseries_predict': getTimeSeriesPredictServingsList,
    'classification': getClassificationServingsList,
    'image_classification': () => { },
    'object_detection': () => { }
  };

  const getTaskMap: Record<string, any> = {
    'anomaly_detection': getAnomalyTaskList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringTaskList,
    'timeseries_predict': getTimeSeriesTaskList,
    'classification': getClassificationTaskList,
    'image_classification': () => { },
    'object_detection': () => { }
  };

  // 删除操作映射
  const deleteMap: Record<string, ((id: number) => Promise<void>) | null> = {
    'anomaly_detection': deleteAnomalyServing,
    'rasa': null, // RASA 类型留空
    'log_clustering': deleteLogClusteringServing,
    'timeseries_predict': deleteTimeSeriesPredictServing,
    'classification': deleteClassificationServing,
    'image_classification': null,
    'object_detection': null
  };

  // 更新操作映射
  const updateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    'anomaly_detection': updateAnomalyServings,
    'rasa': null, // RASA 类型留空
    'log_clustering': updateLogClusteringServings,
    'timeseries_predict': updateTimeSeriesPredictServings,
    'classification': updateClassificationServings,
    'image_classification': null,
    'object_detection': null
  };

  // 容器启动映射
  const containerStartMap: Record<string, ((id: number) => Promise<void>) | null> = {
    'anomaly_detection': null,
    'rasa': null,
    'log_clustering': null,
    'timeseries_predict': startTimeseriesPredictServingContainer,
    'classification': null,
    'image_classification': null,
    'object_detection': null
  };

  // 容器停止映射
  const containerStopMap: Record<string, ((id: number) => Promise<void>) | null> = {
    'anomaly_detection': null,
    'rasa': null,
    'log_clustering': null,
    'timeseries_predict': stopTimeseriesPredictServingContainer,
    'classification': null,
    'image_classification': null,
    'object_detection': null
  };

  const topSection = (
    <TopSection title={t('model-release.title')} content={t('model-release.detail')} />
  );

  const leftSection = (
    <div className='w-full'>
      <Tree
        treeData={treeData}
        showLine
        selectedKeys={selectedKeys}
        onSelect={(keys) => setSelectedKeys(keys as string[])}
        defaultExpandedKeys={['modelRelease']}
      />
    </div>
  );

  const activeTypes = useMemo(() => {
    const [activeTypes] = selectedKeys;
    return activeTypes;
  }, [selectedKeys])

  useEffect(() => {
    setSelectedKeys(['anomaly_detection']);
  }, []);

  useEffect(() => {
    getModelServings();
  }, [selectedKeys])

  const publish = (record: any) => {
    modalRef.current?.showModal({ type: 'add', form: record })
  };

  const handleEdit = (record: any) => {
    modalRef.current?.showModal({ type: 'edit', form: record });
  };

  const getModelServings = async () => {
    // const [activeTypes] = selectedKeys;
    if (!activeTypes || !getServingsMap[activeTypes] || !getTaskMap[activeTypes]) {
      setTableData([]);
      return;
    }

    setLoading(true);
    try {
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
      };

      // 获取任务列表和服务列表
      const [taskList, { count, items }] = await Promise.all([
        getTaskMap[activeTypes]({}),
        getServingsMap[activeTypes](params)
      ]);

      const _data = taskList.map((item: TrainJob) => ({
        label: item.name,
        value: item.id
      }));

      setTrainjobs(_data);
      setTableData(items);
      setPagination((prev) => ({
        ...prev,
        total: count
      }));
    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const handleStartContainer = async (id: number) => {
    // const [activeTypes] = selectedKeys;
    if (!containerStartMap[activeTypes]) return;

    setLoading(true);
    try {
      await containerStartMap[activeTypes](id);
      getModelServings();
    } catch (e) {
      console.log(e);
      message.error(t(`common.fetchFailed`));
    } finally {
      setLoading(false);
    }
  };

  const handleStopContainer = async (id: number) => {
    // const [activeTypes] = selectedKeys;
    if (!containerStopMap[activeTypes]) return;

    setLoading(true);
    try {
      await containerStopMap[activeTypes](id);
      getModelServings();
    } catch (e) {
      console.log(e);
      message.error(t(`common.fetchFailed`))
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    // const [activeTypes] = selectedKeys;
    if (!activeTypes || !deleteMap[activeTypes]) {
      return;
    }

    try {
      await deleteMap[activeTypes]!(id);
      getModelServings();
      message.success(t('common.delSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t(`common.delFailed`));
    }
  };

  const handleModelAcitve = async (id: number, value: boolean) => {
    // const [activeTypes] = selectedKeys;
    if (!activeTypes || !updateMap[activeTypes]) {
      return;
    }

    setLoading(true);
    try {
      const status = value ? 'inactive' : 'active';
      await updateMap[activeTypes]!(id, { status });
      message.success(t('common.updateSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t('common.updateFailed'));
    } finally {
      getModelServings();
    }
  };

  const onRefresh = () => {
    getModelServings();
  };

  return (
    <>
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={
          (
            <>
              <div className="flex justify-end items-center mb-2 gap-2">
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => publish({})}>{t(`model-release.modelRelease`)}</Button>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['View']}>
                  <ReloadOutlined onClick={onRefresh} />
                </PermissionWrapper>
              </div>
              <div className="flex-1 relative">
                <div className="absolute w-full">
                  <CustomTable
                    scroll={{ x: '100%', y: 'calc(100vh - 420px)' }}
                    columns={columns}
                    dataSource={tableData}
                    loading={loading}
                    rowKey='id'
                    pagination={pagination}
                  />
                </div>
              </div>
            </>
          )
        }
      />
      <ReleaseModal ref={modalRef} trainjobs={trainjobs} activeTag={selectedKeys} onSuccess={() => getModelServings()} />
    </>
  )
};

export default ModelRelease;