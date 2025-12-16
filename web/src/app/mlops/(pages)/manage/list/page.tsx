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
import { ModalRef } from '@/app/mlops/types';
import { DataSet } from '@/app/mlops/types/manage';
const { confirm } = Modal;

const DatasetManagePage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const {
    deleteAnomalyDatasets,
    deleteRasaDatasets,
    getAnomalyDatasetsList,
    getRasaDatasetsList,
    getLogClusteringList,
    getTimeSeriesPredictList,
    getClassificationDatasetsList,
    getImageClassificationDatasetsList,
    getObjectDetectionDatasetsList,
    deleteLogClustering,
    deleteTimeSeriesPredict,
    deleteClassificationDataset,
    deleteImageClassificationDataset,
    deleteObjectDetectionDataset
  } = useMlopsManageApi();
  const [datasets, setDatasets] = useState<DataSet[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const modalRef = useRef<ModalRef>(null);
  const datasetTypes = [
    { key: 'anomaly_detection', value: 'anomaly', label: t('datasets.anomaly') },
    { key: 'rasa', value: 'rasa', label: t('datasets.rasa') },
    { key: 'log_clustering', value: 'log_clustering', label: t('datasets.logClustering') },
    { key: 'timeseries_predict', value: 'timeseries_predict', label: t('datasets.timeseriesPredict') },
    { key: 'classification', value: 'classification', label: t('datasets.classification') },
    { key: 'image_classification', value: 'image_classification', label: t('datasets.imageClassification') },
    { key: 'object_detection', value: 'object_detection', label: t('datasets.objectDetection') }
  ];

  const treeData: TreeDataNode[] = [
    {
      title: t(`datasets.datasets`),
      key: 'datasets',
      selectable: false,
      children: [
        {
          title: t(`datasets.anomaly`),
          key: 'anomaly_detection',
        },
        {
          title: t(`datasets.rasa`),
          key: 'rasa',
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
          title: t('datasets.classification'),
          key: 'classification'
        },
        {
          title: t('datasets.imageClassification'),
          key: 'image_classification'
        },
        {
          title: t('datasets.objectDetection'),
          key: 'object_detection'
        }
      ]
    },
  ];

  useEffect(() => {
    setSelectedKeys(['anomaly_detection']);
  }, []);

  useEffect(() => {
    getDataSets();
  }, [selectedKeys]);

  const handleGetDatasetsMap: Record<string, any> = {
    'anomaly_detection': getAnomalyDatasetsList,
    'rasa': getRasaDatasetsList,
    'log_clustering': getLogClusteringList,
    'timeseries_predict': getTimeSeriesPredictList,
    'classification': getClassificationDatasetsList,
    'image_classification': getImageClassificationDatasetsList,
    'object_detection': getObjectDetectionDatasetsList
  };

  const handleDelDatasetsMap: Record<string, any> = {
    'anomaly_detection': deleteAnomalyDatasets,
    'rasa': deleteRasaDatasets,
    'log_clustering': deleteLogClustering,
    'timeseries_predict': deleteTimeSeriesPredict,
    'classification': deleteClassificationDataset,
    'image_classification': deleteImageClassificationDataset,
    'object_detection': deleteObjectDetectionDataset
  };


  const getDataSets = useCallback(async () => {
    const [activeTab] = selectedKeys;
    if (!activeTab) return;
    setLoading(true);
    try {
      const data = await handleGetDatasetsMap[activeTab]({ page: 1, page_size: -1 });
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
      `/mlops/manage/detail?folder_id=${item?.id}&folder_name=${item.name}&description=${item.description}&activeTap=${activeTab}&menu=${activeTab === 'rasa' ? 'intent' : ''}`
    );
  };

  const handleDelete = async (id: number) => {
    confirm({
      title: t('datasets.delDataset'),
      content: t('datasets.delDatasetInfo'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          const [activeTab] = selectedKeys;
          await handleDelDatasetsMap[activeTab](id);
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

  const onSearch = () => {
    // getDataSets();
  };

  const infoText = (item: any) => {
    return <p className='text-right font-mini text-[var(--color-text-3)]'>{`${t(`mlops-common.owner`)}: ${item.creator}`}</p>;
  };

  const menuActions = (item: any) => {
    return (
      <Menu onClick={(e) => e.domEvent.preventDefault()}>
        <Menu.Item
          className="!p-0"
          onClick={() => handleOpenModal({ title: 'editform', type: 'edit', form: item })}
        >
          <PermissionWrapper requiredPermissions={['Edit']} className="!block" >
            <Button type="text" className="w-full">
              {t(`common.edit`)}
            </Button>
          </PermissionWrapper>
        </Menu.Item>
        {item?.name !== "default" && (
          <Menu.Item className="!p-0" onClick={() => handleDelete(item.id)}>
            <PermissionWrapper requiredPermissions={['Delete']} className="!block" >
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
        onSearch={onSearch}
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
