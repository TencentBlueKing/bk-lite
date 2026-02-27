'use client';
import { useState, useRef, useEffect } from "react";
import { useParams } from 'next/navigation';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import useMlopsTaskApi from "@/app/mlops/api/task";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
import CustomTable from "@/components/custom-table";
import EllipsisWithTooltip from "@/components/ellipsis-with-tooltip";
import { useTranslation } from "@/utils/i18n";
import { Button, Popconfirm, message, Tag, Tooltip, Input } from "antd";
import { ReloadOutlined } from '@ant-design/icons';
import ReleaseModal from "@/app/mlops/components/ReleaseModal";
import PermissionWrapper from '@/components/permission';
import { ModalRef, Option, Pagination, TableData, DatasetType } from "@/app/mlops/types";
import { ColumnItem } from "@/types";
import { TrainJob } from "@/app/mlops/types/task";

const { Search } = Input;

const CONTAINER_STATE_MAP: Record<string, string> = {
  'running': 'green',
  'completed': 'blue',
  'not_found': 'default',
  'unknown': 'orange',
  'error': 'red',
  "terminating": 'orange',
  'pending': 'default',
  'failed': 'red'
};

const CONTAINER_TEXT_KEYS: Record<string, string> = {
  'running': 'mlops-common.containerRunning',
  'completed': 'mlops-common.containerCompleted',
  'not_found': 'mlops-common.containerStopped',
  'unknown': 'mlops-common.containerUnknown',
  'error': 'mlops-common.containerError',
  'terminating': "mlops-common.terminating",
  "pending": "mlops-common.pendingDeploy",
  "failed": "mlops-common.failed"
};

const ServingPage = () => {
  const { t } = useTranslation();
  const params = useParams();
  const algorithmType = params.algorithmType as DatasetType;
  const modalRef = useRef<ModalRef>(null);
  const { convertToLocalizedTime } = useLocalizedTime();
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
    startServingContainer,
    stopServingContainer
  } = useMlopsModelReleaseApi();

  const [trainjobs, setTrainjobs] = useState<Option[]>([]);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchName, setSearchName] = useState<string>('');
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  // Update function mapping
  const updateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    [DatasetType.ANOMALY_DETECTION]: updateAnomalyServings,
    [DatasetType.LOG_CLUSTERING]: updateLogClusteringServings,
    [DatasetType.TIMESERIES_PREDICT]: updateTimeSeriesPredictServings,
    [DatasetType.CLASSIFICATION]: updateClassificationServings,
    [DatasetType.IMAGE_CLASSIFICATION]: updateImageClassificationServings,
    [DatasetType.OBJECT_DETECTION]: updateObjectDetectionServings
  };

  const columns: ColumnItem[] = [
    {
      title: t(`model-release.modelName`),
      dataIndex: 'name',
      key: 'name'
    },
    // {
    //   title: t(`model-release.modelDescription`),
    //   dataIndex: 'description',
    //   key: 'description'
    // },
    {
      title: t(`model-release.publishStatus`),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (_, record) => {
        const isActive = record.status === 'active'
        return <Tag color={isActive ? 'green' : 'default'}>{isActive ? t(`mlops-common.published`) : t(`mlops-common.waitRelease`)}</Tag>
      }
    },
    {
      title: t(`mlops-common.containerStatus`),
      dataIndex: 'container_info',
      key: 'container_info',
      width: 120,
      render: (_, record) => {
        const { status, state, detail } = record.container_info;
        const isSuccess = status === 'success';
        const _status = isSuccess ? state : status;
        const text = isSuccess ? state : 'error';
        return (
          <Tooltip title={detail || ''}>
            <Tag color={CONTAINER_STATE_MAP[_status]}>{t(CONTAINER_TEXT_KEYS[text])}</Tag>
          </Tooltip>
        )
      }
    },
    {
      title: t(`mlops-common.port`),
      dataIndex: 'port',
      key: 'port',
      width: 100,
      render: (_, record) => {
        const port = record.container_info?.port || '';
        return port ? <span>{port}</span> : <span>--</span>;
      }
    },
    {
      title: t(`mlops-common.createdAt`),
      key: 'created_at',
      dataIndex: 'created_at',
      width: 170,
      render: (_, record) => {
        return <span>{convertToLocalizedTime(record.created_at, 'YYYY-MM-DD HH:mm:ss')}</span>
      }
    },
    {
      title: t(`mlops-common.creator`),
      key: 'created_by',
      dataIndex: 'created_by',
      width: 120,
      render: (_, { created_by }) => {
        return created_by ? (
          <div className="flex h-full items-center" title={created_by}>
            <span
              className="block w-4.5 h-4.5 leading-4.5 text-center content-center rounded-[50%] mr-2 text-white"
              style={{ background: 'blue' }}
            >
              {created_by.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span>
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={created_by}
              />
            </span>
          </div>
        ) : (
          <>--</>
        );
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
        return (
          <>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`model-release.configuration`)}</Button>
            </PermissionWrapper>
            {status !== 'active' ?
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button type="link" className="mr-2" onClick={() => handleModelActive(record.id, isActive)}>{t(`model-release.release`)}</Button>
              </PermissionWrapper> :
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button type="link" className="mr-2" danger onClick={() => handleModelActive(record.id, isActive)}>{t(`model-release.discontinued`)}</Button>
              </PermissionWrapper>
            }
            {state !== 'running' && state !== 'unknown' ?
              <PermissionWrapper requiredPermissions={['Start']}>
                <Button type="link" className="mr-2" onClick={() => handleStartContainer(record.id)}>{t(`mlops-common.start`)}</Button>
              </PermissionWrapper> :
              <PermissionWrapper requiredPermissions={['Stop']}>
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
          </>
        )
      }
    }
  ];

  useEffect(() => {
    getModelServings();
  }, [algorithmType, pagination.current, pagination.pageSize]);

  const publish = (record: any) => {
    modalRef.current?.showModal({ type: 'add', form: record })
  };

  const handleEdit = (record: any) => {
    modalRef.current?.showModal({ type: 'edit', form: record });
  };

  const getModelServings = async (name = searchName) => {
    if (!algorithmType) {
      setTableData([]);
      return;
    }

    setLoading(true);
    try {
      const params = {
        key: algorithmType,
        page: pagination.current,
        page_size: pagination.pageSize,
        name: name || undefined,
      };

      const [taskList, { count, items }] = await Promise.all([
        getTrainJobList({ key: algorithmType }),
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
    setLoading(true);
    try {
      await startServingContainer(id, algorithmType);
      getModelServings();
    } catch (e) {
      console.error(e);
      message.error(t(`common.fetchFailed`));
    } finally {
      setLoading(false);
    }
  };

  const handleStopContainer = async (id: number) => {
    if (!algorithmType) return;

    setLoading(true);
    try {
      await stopServingContainer(id, algorithmType);
      getModelServings();
    } catch (e) {
      console.error(e);
      message.error(t(`common.fetchFailed`))
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!algorithmType) return;

    try {
      await deleteServing(id, algorithmType);
      getModelServings();
      message.success(t(`common.delSuccess`));
    } catch (e) {
      console.error(e);
      message.error(t(`common.delFailed`));
    }
  };

  const handleModelActive = async (id: number, value: boolean) => {
    if (!algorithmType || !updateMap[algorithmType]) {
      return;
    }

    setLoading(true);
    try {
      const status = value ? 'inactive' : 'active';
      await updateMap[algorithmType]!(id, { status });
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

  const onSearch = (value: string) => {
    setSearchName(value);
    setPagination(prev => ({ ...prev, current: 1 }));
    getModelServings(value);
  };

  const handleTableChange = (value: Pagination) => {
    setPagination(value);
  };

  return (
    <>
      <div className="flex justify-end items-center mb-4 gap-2">
        <div className="flex items-center">
          <Search
            className="w-60 mr-1.5"
            placeholder={t('model-release.searchText')}
            enterButton
            onSearch={onSearch}
            style={{ fontSize: 15 }}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" className="mr-2" onClick={() => publish({})}>{t(`model-release.modelRelease`)}</Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['View']}>
            <ReloadOutlined onClick={onRefresh} />
          </PermissionWrapper>
        </div>
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
            onChange={handleTableChange}
          />
        </div>
      </div>
      <ReleaseModal ref={modalRef} trainjobs={trainjobs} activeTag={[algorithmType]} onSuccess={() => getModelServings()} />
    </>
  )
};

export default ServingPage;
