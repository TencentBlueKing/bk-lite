import { useCallback, useState, useMemo, useRef, useEffect } from "react";
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from "@/utils/i18n";
import useMlopsManageApi from '@/app/mlops/api/manage';
import CustomTable from "@/components/custom-table";
import PermissionWrapper from '@/components/permission';
import UploadModal from "../../uploadModal";
import OperateModal from "@/components/operate-modal";
import {
  Input,
  Button,
  Popconfirm,
  Tag,
  Breadcrumb,
  Checkbox,
  type CheckboxOptionType,
  message,
} from "antd";
import { TYPE_CONTENT, TYPE_COLOR } from "@/app/mlops/constants";
import { ColumnItem, ModalRef, Pagination, TableData } from '@/app/mlops/types';
const { Search } = Input;

const AnomalyDetail = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const modalRef = useRef<ModalRef>(null);
  const searchParams = useSearchParams();
  const { getAnomalyTrainData, deleteAnomalyTrainData, labelingData } = useMlopsManageApi();
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [currentData, setCurrentData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  const {
    folder_id,
    folder_name,
    description,
    activeTap
  } = useMemo(() => ({
    folder_id: searchParams.get('folder_id'),
    folder_name: searchParams.get('folder_name') || '',
    description: searchParams.get('description') || '',
    activeTap: searchParams.get('activeTap') || ''
  }), [searchParams]);

  const columns: ColumnItem[] = useMemo(() => [
    {
      title: t('common.name'),
      key: 'name',
      dataIndex: 'name',
    },
    {
      title: t('datasets.anomalyTitle'),
      key: 'count',
      dataIndex: 'count',
    },
    {
      title: t('datasets.trainFileType'),
      key: 'type',
      dataIndex: 'type',
      render: (_, record) => {
        const activeTypes = Object.entries(record.type)
          .filter(([, value]) => value === true)
          .map(([key]) => <Tag key={key} color={TYPE_COLOR[key]}>{t(`datasets.${TYPE_CONTENT[key]}`)}</Tag>);
        return (<>{activeTypes.length ? activeTypes : '--'}</>)
      },
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 200,
      fixed: 'right',
      render: (_: unknown, record) => (
        <>
          <Button
            type="link"
            className="mr-[10px]"
            onClick={() => toAnnotation(record)}
          >
            {t('datasets.annotate')}
          </Button>
          <PermissionWrapper requiredPermissions={['File Edit']}>
            <Button
              type="link"
              className="mr-[10px]"
              onClick={() => openModal(record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['File Delete']}>
            <Popconfirm
              title={t('datasets.deleteTitle')}
              description={t('datasets.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </>
      ),
    },
  ], [t]);

  const options: CheckboxOptionType[] = [
    { label: t(`datasets.train`), value: 'is_train_data' },
    { label: t(`datasets.validate`), value: 'is_val_data' },
    { label: t(`datasets.test`), value: 'is_test_data' },
  ];

  useEffect(() => {
    getDataset();
  }, [pagination.current, pagination.pageSize]);

  const onChange = (checkedValues: string[]) => {
    setSelectedTags(checkedValues);
  };

  const onSearch = (search: string) => {
    getDataset(search);
  };

  const getDataset = useCallback(async (search: string = '') => {
    setLoading(true);
    try {
      const { count, items } = await getAnomalyTrainData({
        name: search,
        dataset: folder_id as string,
        page: pagination.current,
        page_size: pagination.pageSize
      });
      const _tableData = items?.map((item: any) => {
        return {
          id: item?.id,
          name: item?.name,
          dataset: item?.dataset,
          count: item?.anomaly_point_count,
          type: {
            is_test_data: item?.is_test_data,
            is_train_data: item?.is_train_data,
            is_val_data: item?.is_val_data
          }
        }
      });
      setTableData(_tableData as TableData[]);
      setPagination((prev) => {
        return {
          ...prev,
          total: count || 0
        }
      });
    }
    catch (e) { console.log(e) }
    finally { setLoading(false) }
  }, [t, searchParams]);

  const onUpload = () => {
    const data = {
      dataset_id: folder_id,
      folder: folder_name,
      activeTap
    };
    modalRef.current?.showModal({ type: 'edit', form: data });
  };

  const onDelete = async (data: any) => {
    setConfirmLoading(true);
    try {
      await deleteAnomalyTrainData(data.id);
    } catch (e) {
      console.log(e);
    } finally {
      setConfirmLoading(false);
      getDataset();
    }
  };

  const toAnnotation = (data: any) => {
    router.push(`/mlops/manage/annotation?id=${data.id}&folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`);
  };

  const handleChange = (value: any) => {
    setPagination(value);
  };

  const handleCancel = () => {
    setModalOpen(false);
  };

  const handleSubmit = async () => {
    setConfirmLoading(true);
    try {
      if (activeTap === 'anomaly') {
        const params = {
          is_train_data: selectedTags.includes('is_train_data'),
          is_val_data: selectedTags.includes('is_val_data'),
          is_test_data: selectedTags.includes('is_test_data')
        };
        await labelingData(currentData?.id, params);
        message.success(t(`common.updateSuccess`));
        setModalOpen(false);
        getDataset();
      }
    } catch (e) {
      console.log(e);
    } finally {
      setConfirmLoading(false);
    }
  };

  const openModal = (data: any) => {
    setCurrentData(data);
    setModalOpen(true);
    const { is_train_data, is_val_data, is_test_data } = data.type;
    const activeTypes = Object.entries({ is_train_data, is_val_data, is_test_data })
      .filter(([, value]) => value === true)
      .map(([key]) => key);
    setSelectedTags(activeTypes);
  };

  return (
    <>
      <div className="flex justify-between items-center mb-4 gap-2">
        <div>
          <Breadcrumb
            separator=">"
            items={[
              { title: <a href="#" onClick={() => router.push(`/mlops/manage/list`)}>{t(`datasets.datasets`)}</a> },
              { title: t(`datasets.datasetsDetail`) }
            ]}
          />
        </div>
        <div className='flex'>
          <Search
            className="w-[240px] mr-1.5"
            placeholder={t('common.search')}
            enterButton
            onSearch={onSearch}
            style={{ fontSize: 15 }}
          />
          <PermissionWrapper requiredPermissions={['File Upload']}>
            <Button type="primary" className="rounded-md text-xs shadow" onClick={onUpload}>
              {t("datasets.upload")}
            </Button>
          </PermissionWrapper>
        </div>
      </div>
      <div className="flex-1 relative">
        <div className='absolute w-full'>
          <CustomTable
            rowKey="id"
            className="mt-3"
            scroll={{ x: '100%', y: 'calc(100vh - 420px)' }}
            dataSource={tableData}
            columns={columns}
            pagination={pagination}
            loading={loading}
            onChange={handleChange}
          />
        </div>
      </div>
      <UploadModal ref={modalRef} onSuccess={() => getDataset()} />
      <OperateModal
        open={modalOpen}
        title={t(`common.edit`)}
        onCancel={handleCancel}
        footer={[
          <Button key="submit" loading={confirmLoading} type="primary" onClick={handleSubmit}>
            {t('common.confirm')}
          </Button>,
          <Button key="cancel" onClick={handleCancel}>
            {t('common.cancel')}
          </Button>,
        ]}
      >
        <div>
          {t(`datasets.fileType`) + ': '}
          <Checkbox.Group options={options} value={selectedTags} onChange={onChange} />
        </div>
      </OperateModal>
    </>
  )
};

export default AnomalyDetail;