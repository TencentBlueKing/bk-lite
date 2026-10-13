"use client";
import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, useParams } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { PlusOutlined } from '@ant-design/icons';
import {
  message,
  Button,
  Modal,
} from 'antd';
import DatasetModal from '@/app/mlops/components/DatasetModal';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import EntityList from '@/components/entity-list';
import GridEntityCard from '@/components/grid-entity-card';
import Icon from '@/components/icon';
import PermissionWrapper from '@/components/permission';
import { DatasetType, ModalRef } from '@/app/mlops/types';
import { DataSet } from '@/app/mlops/types/manage';
import { useUserInfoContext } from '@/context/userInfo';
import { formatGroupNames } from '@/app/mlops/utils/common';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
const { confirm } = Modal;

const DatasetsPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams();
  const algorithmType = params.algorithmType as DatasetType;
  const { flatGroups } = useUserInfoContext();

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
          team: item?.team || [],
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

  const menuItems = (item: DataSet): MoreActionsDropdownItem[] => {
    const items: MoreActionsDropdownItem[] = [
      {
        key: 'edit',
        label: t('common.edit'),
        permission: 'Edit',
        onClick: () => handleOpenModal({ title: 'editform', type: 'edit', form: item }),
      },
    ];
    if (item?.name !== 'default') {
      items.push({
        key: 'delete',
        label: t('common.delete'),
        permission: 'Delete',
        danger: true,
        onClick: () => handleDelete(item.id),
      });
    }
    return items;
  };

  return (
    <>
      <div className='overflow-auto h-[calc(100vh-200px)] pb-2'>
        <EntityList
          data={datasets}
          loading={loading}
          loadingContent={<CardGridSkeleton count={8} />}
          onSearch={() => { }}
          renderCard={(item) => (
            <GridEntityCard
              name={item.name}
              description={item.description}
              icon={<Icon type={item.icon} className="text-2xl" />}
              owner={item.creator}
              team={formatGroupNames(item.team, flatGroups)}
              ownerLabel={t('mlops-common.owner')}
              teamLabel={t('mlops-common.organizations')}
              footer="entity"
              menuItems={menuItems(item)}
              onClick={() => navigateToNode(item)}
            />
          )}
          operateSection={(
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => handleOpenModal({ type: 'add', title: 'addform', form: {} })}
              >
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          )}
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
