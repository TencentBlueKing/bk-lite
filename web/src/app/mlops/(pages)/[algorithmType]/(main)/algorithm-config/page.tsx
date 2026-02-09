'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useAlgorithmConfigApi from '@/app/mlops/api/algorithmConfig';
import { Button, Input, Popconfirm, message, Tag, Switch } from 'antd';
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import AlgorithmConfigModal from '@/app/mlops/components/algorithm-config/AlgorithmConfigModal';
import { useTranslation } from '@/utils/i18n';
import type { ColumnItem } from '@/app/mlops/types';
import type { AlgorithmConfigListItem, AlgorithmType } from '@/app/mlops/types/algorithmConfig';

const { Search } = Input;

// i18n key mapping for algorithm types
const ALGORITHM_TYPE_I18N_KEYS: Record<string, string> = {
  anomaly_detection: 'algorithmType.anomaly_detection',
  timeseries_predict: 'algorithmType.timeseries_predict',
  log_clustering: 'algorithmType.log_clustering',
  classification: 'algorithmType.classification',
  image_classification: 'algorithmType.image_classification',
  object_detection: 'algorithmType.object_detection',
};

export interface ModalRef {
  showModal: (params: { type: string; title: string; form: AlgorithmConfigListItem | null }) => void;
}

const AlgorithmConfigPage = () => {
  const { t } = useTranslation();
  const params = useParams();
  const algorithmType = params.algorithmType as AlgorithmType;
  
  const { convertToLocalizedTime } = useLocalizedTime();
  const {
    getAlgorithmConfigList,
    deleteAlgorithmConfig,
    updateAlgorithmConfig,
  } = useAlgorithmConfigApi();

  const modalRef = useRef<ModalRef>(null);
  const [tableData, setTableData] = useState<AlgorithmConfigListItem[]>([]);
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
      width: 120,
    },
    {
      title: t('algorithmConfig.displayName'),
      key: 'display_name',
      dataIndex: 'display_name',
      width: 120,
    },
    {
      title: t('algorithmConfig.image'),
      key: 'image',
      dataIndex: 'image',
      width: 180,
      ellipsis: true,
      render: (_, record) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={record.image}
        />
      ),
    },
    {
      title: t('algorithmConfig.isActive'),
      key: 'is_active',
      dataIndex: 'is_active',
      width: 100,
      align: 'center',
      render: (_, record: AlgorithmConfigListItem) => (
        <Switch
          checked={record.is_active}
          onChange={(checked) => handleToggleActive(record.id, checked)}
          size="small"
        />
      ),
    },
    {
      title: t('mlops-common.createdAt'),
      key: 'created_at',
      dataIndex: 'created_at',
      width: 120,
      render: (_, record) => (
        <p>{convertToLocalizedTime(record.created_at || '', 'YYYY-MM-DD HH:mm:ss')}</p>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      fixed: 'right',
      align: 'center',
      render: (_: unknown, record: AlgorithmConfigListItem) => (
        <>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              className="mr-2"
              onClick={() => handleEdit(record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('algorithmConfig.deleteConfirm')}
              description={t('algorithmConfig.deleteConfirmContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => onDelete(record.id)}
            >
              <Button type="link" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      ),
    },
  ];

  useEffect(() => {
    getConfigs();
  }, [pagination.current, pagination.pageSize, algorithmType]);

  const getConfigs = useCallback(async (name = '') => {
    if (!algorithmType) return;

    setLoading(true);
    try {
      const data = await getAlgorithmConfigList({
        algorithm_type: algorithmType,
        name: name || undefined,
        page: pagination.current,
        page_size: pagination.pageSize,
      });

      if (data) {
        setTableData(data.items || []);
        setPagination((prev) => ({
          ...prev,
          total: data.count || 0,
        }));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [algorithmType, pagination.current, pagination.pageSize, getAlgorithmConfigList]);

  const handleAdd = () => {
    if (modalRef.current) {
      modalRef.current.showModal({
        type: 'add',
        title: 'addConfig',
        form: null,
      });
    }
  };

  const handleEdit = (record: AlgorithmConfigListItem) => {
    if (modalRef.current) {
      modalRef.current.showModal({
        type: 'edit',
        title: 'editConfig',
        form: record,
      });
    }
  };

  const handleToggleActive = async (id: number, isActive: boolean) => {
    try {
      await updateAlgorithmConfig(id, { is_active: isActive });
      message.success(t('common.updateSuccess'));
      getConfigs();
    } catch (e: unknown) {
      console.error(e);
      // 尝试从错误中提取后端返回的具体信息
      const error = e as { response?: { data?: { error?: string } } };
      const errorMessage = error.response?.data?.error;
      if (errorMessage) {
        message.error(errorMessage);
      } else {
        message.error(t('common.error'));
      }
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteAlgorithmConfig(id);
      message.success(t('common.delSuccess'));
      getConfigs();
    } catch (error: unknown) {
      console.error(error);
      // 显示后端返回的具体错误信息（如：有训练任务正在使用此算法）
      const axiosError = error as { response?: { data?: { error?: string } } };
      const errorMessage = axiosError.response?.data?.error || t('common.delFailed');
      message.error(errorMessage);
    }
  };

  const handleChange = (value: { current: number; pageSize: number; total: number }) => {
    setPagination(value);
  };

  const onSearch = (value: string) => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    getConfigs(value);
  };

  const onRefresh = () => {
    getConfigs();
  };

  return (
    <>
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <Tag color="blue">
            {t(ALGORITHM_TYPE_I18N_KEYS[algorithmType] || algorithmType)}
          </Tag>
          <span className="text-gray-500 text-sm">
            {t('algorithmConfig.pageDescription')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Search
            className="w-60"
            placeholder={t('algorithmConfig.searchPlaceholder')}
            enterButton
            onSearch={onSearch}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAdd}
            >
              {t('common.add')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['View']}>
            <ReloadOutlined onClick={onRefresh} />
          </PermissionWrapper>
        </div>
      </div>
      <div className="flex-1 relative">
        <div className="absolute w-full">
          <CustomTable
            rowKey="id"
            scroll={{ x: '100%', y: 'calc(100vh - 410px)' }}
            dataSource={tableData}
            columns={columns}
            pagination={pagination}
            loading={loading}
            onChange={handleChange}
          />
        </div>
      </div>
      <AlgorithmConfigModal
        ref={modalRef}
        algorithmType={algorithmType}
        onSuccess={onRefresh}
      />
    </>
  );
};

export default AlgorithmConfigPage;
