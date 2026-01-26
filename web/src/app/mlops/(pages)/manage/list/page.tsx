"use client";
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';
import useMlopsManageApi from '@/app/mlops/api/manage';
import {
  message,
  Button,
  Menu,
  Modal,
  Tree
} from 'antd';
import type { TreeDataNode } from 'antd';
import DatasetModal from './dataSetsModal';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import EntityList from '@/components/entity-list';
import PermissionWrapper from '@/components/permission';
import { DatasetType, ModalRef } from '@/app/mlops/types';
import { DataSet } from '@/app/mlops/types/manage';
const { confirm } = Modal;

const DatasetManagePage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const {
    getDatasetsList,
    deleteDataset,
  } = useMlopsManageApi();
  const [datasets, setDatasets] = useState<DataSet[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const modalRef = useRef<ModalRef>(null);
  const datasetTypes = [
    { key: DatasetType.ANOMALY_DETECTION, value: 'anomaly', label: t('datasets.anomaly') },
    // { key: DatasetType.RASA, value: 'rasa', label: t('datasets.rasa') },
    { key: DatasetType.LOG_CLUSTERING, value: 'log_clustering', label: t('datasets.logClustering') },
    { key: DatasetType.TIMESERIES_PREDICT, value: 'timeseries_predict', label: t('datasets.timeseriesPredict') },
    { key: DatasetType.CLASSIFICATION, value: 'classification', label: t('datasets.classification') },
    { key: DatasetType.IMAGE_CLASSIFICATION, value: 'image_classification', label: t('datasets.imageClassification') },
    { key: DatasetType.OBJECT_DETECTION, value: 'object_detection', label: t('datasets.objectDetection') }
  ];

  const treeData: TreeDataNode[] = [
    {
      title: t(`datasets.datasets`),
      key: 'datasets',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: DatasetType.ANOMALY_DETECTION,
        },
        {
          title: t(`datasets.rasa`),
          key: DatasetType.RASA,
        },
        {
          title: t(`datasets.timeseriesPredict`),
          key: DatasetType.TIMESERIES_PREDICT,
        },
        {
          title: t(`datasets.logClustering`),
          key: DatasetType.LOG_CLUSTERING,
        },
        {
          title: t('datasets.classification'),
          key: DatasetType.CLASSIFICATION
        },
        {
          title: t('datasets.imageClassification'),
          key: DatasetType.IMAGE_CLASSIFICATION
        },
        {
          title: t('datasets.objectDetection'),
          key: DatasetType.OBJECT_DETECTION
        }
      ]
    },
  ];

  useEffect(() => {
    setSelectedKeys([DatasetType.ANOMALY_DETECTION]);
  }, []);

  useEffect(() => {
    getDataSets();
  }, [selectedKeys]);


  const getDataSets = useCallback(async () => {
    const [activeTab] = selectedKeys;
    if (!activeTab) return;
    setLoading(true);
    try {
      const data = await getDatasetsList({ key: activeTab as DatasetType, page: 1, page_size: -1 });
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
      console.log(e);
      setDatasets([]);
    } finally {
      setLoading(false);
    }
  }, [selectedKeys]);

  const navigateToNode = (item: any) => {
    const [activeTab] = selectedKeys;
    router.push(
      `/mlops/manage/detail?folder_id=${item?.id}&folder_name=${item.name}&description=${item.description}&activeTap=${activeTab}&menu=${activeTab === DatasetType.RASA ? 'intent' : ''}`
    );
  };

  const handleDelete = async (id: number) => {
    confirm({
      title: t('datasets.delDataset'),
      content: (
        <div>
          <p>{t('datasets.delDatasetInfo')}</p>
          <div className="mt-3 p-3 bg-orange-50 border border-orange-200 rounded">
            <p className="text-orange-600 font-medium mb-2">⚠️ {t('mlops-common.warning')}</p>
            <ul className="text-sm text-gray-700 space-y-1 ml-4">
              <li>• {t('datasets.delWarning1')}</li>
              <li>• {t('datasets.delWarning2')}</li>
            </ul>
          </div>
        </div>
      ),
      okText: t('common.confirm'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          const [activeTab] = selectedKeys;
          await deleteDataset(id, activeTab as DatasetType);
          message.success(t('common.delSuccess'));
        } catch (e) {
          console.log(e);
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

  const topSection = (<TopSection title={t('datasets.datasets')} content={t('traintask.description')} />);

  const leftSection = (
    <div className='w-full'>
      <Tree
        treeData={treeData}
        showLine
        selectedKeys={selectedKeys}
        onSelect={(keys) => setSelectedKeys(keys as string[])}
        defaultExpandedKeys={['datasets']}
      />
    </div>
  );

  const rightSection = (
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
  );

  return (
    <>
      <PageLayout
        topSection={topSection}
        leftSection={leftSection}
        rightSection={rightSection}
      />
      <DatasetModal
        ref={modalRef}
        options={datasetTypes}
        onSuccess={getDataSets}
        activeTag={selectedKeys}
      />
    </>
  );
};

export default DatasetManagePage;
