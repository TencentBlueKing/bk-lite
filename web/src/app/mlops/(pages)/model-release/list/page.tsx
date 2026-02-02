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
import { ModalRef, Option, Pagination, TableData, DatasetType } from "@/app/mlops/types";
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
  'not_found': '已停止',
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
  const { getTrainJobList } = useMlopsTaskApi();
  const {
    getServingList,
    deleteServing,
    updateAnomalyServings,
    updateTimeSeriesPredictServings,
    updateLogClusteringServings,
    updateClassificationServings,
    updateImageClassificationServings,
    updateObjectDetectionServings,

    startServingContainer, stopServingContainer
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
          key: DatasetType.ANOMALY_DETECTION,
        },
        // {
        //   title: t(`datasets.rasa`),
        //   key: DatasetType.RASA
        // },
        {
          title: t(`datasets.timeseriesPredict`),
          key: DatasetType.TIMESERIES_PREDICT
        },
        {
          title: t(`datasets.logClustering`),
          key: DatasetType.LOG_CLUSTERING
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
          title: t(`datasets.objectDetection`),
          key: DatasetType.OBJECT_DETECTION
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
        return <Tag color={isAcitve ? 'green' : 'default'}>{isAcitve ? t(`mlops-common.published`) : t(`mlops-common.waitRelease`)}</Tag>
      }
    },
    {
      title: t(`mlops-common.containerStatus`),
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
          {state !== 'running' && state !== 'unknown' ?
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


  // 更新操作映射
  const updateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    [DatasetType.ANOMALY_DETECTION]: updateAnomalyServings,
    [DatasetType.LOG_CLUSTERING]: updateLogClusteringServings,
    [DatasetType.TIMESERIES_PREDICT]: updateTimeSeriesPredictServings,
    [DatasetType.CLASSIFICATION]: updateClassificationServings,
    [DatasetType.IMAGE_CLASSIFICATION]: updateImageClassificationServings,
    [DatasetType.OBJECT_DETECTION]: updateObjectDetectionServings
  };

  const topSection = (
    <TopSection title={t(`model-release.title`)} content={t(`model-release.detail`)} />
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
    setSelectedKeys([DatasetType.ANOMALY_DETECTION]);
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
    const [activeTypes] = selectedKeys;
    if (!activeTypes) {
      setTableData([]);
      return;
    }

    setLoading(true);
    try {
      const params = {
        key: activeTypes as DatasetType,
        page: pagination.current,
        page_size: pagination.pageSize,
      };

      // 获取任务列表和服务列表
      const [taskList, { count, items }] = await Promise.all([
        getTrainJobList({ key: activeTypes as DatasetType }),
        getServingList(params)
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
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleStartContainer = async (id: number) => {
    const [activeTypes] = selectedKeys;

    setLoading(true);
    try {
      await startServingContainer(id, activeTypes as DatasetType);
      getModelServings();
    } catch (e) {
      console.error(e);
      message.error(t(`common.fetchFailed`));
    } finally {
      setLoading(false);
    }
  };

  const handleStopContainer = async (id: number) => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes) return;

    setLoading(true);
    try {
      await stopServingContainer(id, activeTypes as DatasetType);
      getModelServings();
    } catch (e) {
      console.error(e);
      message.error(t(`common.fetchFailed`))
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    const [activeTypes] = selectedKeys;
    if (!activeTypes) return;

    try {
      await deleteServing(id, activeTypes as DatasetType);
      getModelServings();
      message.success(t(`common.delSuccess`));
    } catch (e) {
      console.error(e);
      message.error(t(`common.delFailed`));
    }
  };

  const handleModelAcitve = async (id: number, value: boolean) => {
    if (!activeTypes || !updateMap[activeTypes]) {
      return;
    }

    setLoading(true);
    try {
      const status = value ? 'inactive' : 'active';
      await updateMap[activeTypes]!(id, { status });
      message.success(t(`common.updateSuccess`));
    } catch (e) {
      console.error(e);
      message.error(t(`common.updateFailed`));
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