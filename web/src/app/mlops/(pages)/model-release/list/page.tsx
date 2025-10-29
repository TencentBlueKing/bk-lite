'use client';
import { useState, useRef, useEffect } from "react";
import useMlopsTaskApi from "@/app/mlops/api/task";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { Button, Popconfirm, Switch, message, Tree, type TreeDataNode } from "antd";
import { PlusOutlined } from '@ant-design/icons';
import PageLayout from '@/components/page-layout';
import TopSection from "@/components/top-section";
import ReleaseModal from "./releaseModal";
import PermissionWrapper from '@/components/permission';
import { ModalRef, Option, Pagination, TableData } from "@/app/mlops/types";
import { ColumnItem } from "@/types";
import { TrainJob } from "@/app/mlops/types/task";


const ModelRelease = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const { getAnomalyTaskList, getLogClusteringTaskList, getTimeSeriesTaskList, getClassificationTaskList } = useMlopsTaskApi();
  const {
    getAnomalyServingsList, deleteAnomalyServing, updateAnomalyServings,
    getTimeSeriesPredictServingsList, deleteTimeSeriesPredictServing, updateTimeSeriesPredictServings,
    getLogClusteringServingsList, deleteLogClusteringServing, updateLogClusteringServings,
    getClassificationServingsList, deleteClassificationServing, updateClassificationServings
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
          key: 'anomaly',
        },
        {
          title: t(`datasets.rasa`),
          key: 'rasa'
        },
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
        return <Switch checked={record.status === 'active'} onChange={(value: boolean) => handleModelAcitve(record.id, value)} />
      }
    },
    {
      title: t(`common.action`),
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (_, record: TableData) => {
        return (<>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`common.edit`)}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t(`model-release.delModel`)}
              description={t(`model-release.delModelContent`)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger>{t(`common.delete`)}</Button>
            </Popconfirm>
          </PermissionWrapper>
        </>)
      }
    }
  ];

  const getServingsMap: Record<string, any> = {
    'anomaly': getAnomalyServingsList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringServingsList,
    'timeseries_predict': getTimeSeriesPredictServingsList,
    'classification': getClassificationServingsList
  };

  const getTaskMap: Record<string, any> = {
    'anomaly': getAnomalyTaskList,
    'rasa': null, // RASA 类型留空
    'log_clustering': getLogClusteringTaskList,
    'timeseries_predict': getTimeSeriesTaskList,
    'classification': getClassificationTaskList
  };

  // 删除操作映射
  const deleteMap: Record<string, ((id: number) => Promise<void>) | null> = {
    'anomaly': deleteAnomalyServing,
    'rasa': null, // RASA 类型留空
    'log_clustering': deleteLogClusteringServing,
    'timeseries_predict': deleteTimeSeriesPredictServing,
    'classification': deleteClassificationServing
  };

  // 更新操作映射
  const updateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    'anomaly': updateAnomalyServings,
    'rasa': null, // RASA 类型留空
    'log_clustering': updateLogClusteringServings,
    'timeseries_predict': updateTimeSeriesPredictServings,
    'classification': updateClassificationServings
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

  useEffect(() => {
    setSelectedKeys(['anomaly']);
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

  const handleDelete = async (id: number) => {
    const [activeTypes] = selectedKeys;
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
    const [activeTypes] = selectedKeys;
    if (!activeTypes || !updateMap[activeTypes]) {
      return;
    }

    setLoading(true);
    try {
      const status = value ? 'active' : 'inactive';
      await updateMap[activeTypes]!(id, { status });
      message.success(t('common.updateSuccess'));
    } catch (e) {
      console.log(e);
      message.error(t('common.updateFailed'));
    } finally {
      getModelServings();
    }
  };

  return (
    <>
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={
          (
            <>
              <div className="flex justify-end mb-2">
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => publish({})}>{t(`model-release.modelRelease`)}</Button>
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