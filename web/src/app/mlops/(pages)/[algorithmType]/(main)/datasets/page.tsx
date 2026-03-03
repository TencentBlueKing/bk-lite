"use client";
import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, useParams } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import {
  message,
  Button,
  Menu,
  Modal,
} from 'antd';
import DatasetModal from '@/app/mlops/components/DatasetModal';
import EntityList from '@/components/entity-list';
import PermissionWrapper from '@/components/permission';
import { DatasetType, ModalRef } from '@/app/mlops/types';
import { DataSet } from '@/app/mlops/types/manage';
const { confirm } = Modal;

const DatasetsPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams();
  const algorithmType = params.algorithmType as DatasetType;

  const {
    getDatasetsList,
    deleteDataset,
  } = useMlopsManageApi();
  const [datasets, setDatasets] = useState<DataSet[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const modalRef = useRef<ModalRef>(null);

  const datasetTypes = [
    { key: DatasetType.ANOMALY_DETECTION, value: 'anomaly', label: t('datasets.anomaly') },
    { key: DatasetType.LOG_CLUSTERING, value: 'log_clustering', label: t('datasets.logClustering') },
    { key: DatasetType.TIMESERIES_PREDICT, value: 'timeseries_predict', label: t('datasets.timeseriesPredict') },
    { key: DatasetType.CLASSIFICATION, value: 'classification', label: t('datasets.classification') },
    { key: DatasetType.IMAGE_CLASSIFICATION, value: 'image_classification', label: t('datasets.imageClassification') },
    { key: DatasetType.OBJECT_DETECTION, value: 'object_detection', label: t('datasets.objectDetection') }
  ];

  useEffect(() => {
    getDataSets();
  }, [algorithmType]);

  const getDataSets = useCallback(async () => {
    if (!algorithmType) return;
    setLoading(true);
    try {
      const data = await getDatasetsList({ key: algorithmType, page: 1, page_size: -1 });
      const _data: DataSet[] = data?.map((item: any) => {
        return {
          id: item.id,
          name: item.name,
          description: item.description || '--',
          icon: 'tucengshuju',
          creator: item?.created_by || '--',
        }
      }) || [];
      setDatasets(_data);
    } catch (e) {
      console.error(e);
      setDatasets([]);
    } finally {
      setLoading(false);
    }
  }, [algorithmType, getDatasetsList]);

  const navigateToNode = useCallback((item: any) => {
    router.push(
      `/mlops/${algorithmType}/detail?dataset_id=${item?.id}&folder_name=${encodeURIComponent(item.name)}&description=${encodeURIComponent(item.description)}`
    );
  }, [algorithmType, router]);

  const handleDelete = async (id: number) => {
    confirm({
      title: t('datasets.delDataset'),
      content: (
        <div>
          <p>{t('datasets.delDatasetInfo')}</p>
        </div>
      ),
      okText: t('common.confirm'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await deleteDataset(id, algorithmType);
          message.success(t('common.delSuccess'));
        } catch (e) {
          console.error(e);
          message.error(t(`common.delFailed`));
        } finally {
          getDataSets();
        }
      }
    })
  };

  const handleOpenModal = (object: {
    type: string,
    title: string,
    form: any
  }) => {
    modalRef.current?.showModal(object);
  };

  const infoText = (item: any) => {
    return <p className='text-right font-mini text-(--color-text-3)'>{`${t(`mlops-common.owner`)}: ${item.creator}`}</p>;
  };

  const menuActions = (item: any) => {
    return (
      <Menu onClick={(e) => e.domEvent.preventDefault()}>
        <Menu.Item
          className="p-0!"
          onClick={() => handleOpenModal({ title: 'editform', type: 'edit', form: item })}
        >
          <PermissionWrapper requiredPermissions={['Edit']} className="block!" >
            <Button type="text" className="w-full">
              {t(`common.edit`)}
            </Button>
          </PermissionWrapper>
        </Menu.Item>
        {item?.name !== "default" && (
          <Menu.Item className="p-0!" onClick={() => handleDelete(item.id)}>
            <PermissionWrapper requiredPermissions={['Delete']} className="block!" >
              <Button type="text" className="w-full">
                {t(`common.delete`)}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
        )}
      </Menu>
    )
  };

  return (
    <>
      <div className='overflow-auto h-[calc(100vh-200px)] pb-2'>
        <EntityList
          data={datasets}
          menuActions={menuActions}
          loading={loading}
          onCardClick={navigateToNode}
          openModal={() => handleOpenModal({ type: 'add', title: 'addform', form: {} })}
          onSearch={() => { }}
          descSlot={infoText}
        />
      </div>
      <DatasetModal
        ref={modalRef}
        options={datasetTypes}
        onSuccess={getDataSets}
        activeTag={[algorithmType]}
      />
    </>
  );
};

export default DatasetsPage;
