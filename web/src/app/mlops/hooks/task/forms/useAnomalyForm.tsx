import { useState, useCallback, useEffect, RefObject } from 'react';
import { FormInstance, message, Form, Select, Input, InputNumber, Divider, Transfer, Spin } from 'antd';
import type { TransferProps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';
import useTrainDataLoader from '@/app/mlops/hooks/task/useTrainDataLoader';
import useParamsUtil from '@/app/mlops/hooks/task/useParamsUtil';
import { Option } from '@/app/mlops/types';
import { TrainJob, AlgorithmParam } from '@/app/mlops/types/task';
import RangeInput from '@/app/mlops/components/range-input';
import { ALGORITHMS_PARAMS } from '@/app/mlops/constants';

interface ModalState {
  isOpen: boolean;
  type: string;
  title: string;
}

interface UseAnomalyFormProps {
  datasetOptions: Option[];
  activeTag: string[];
  onSuccess: () => void;
  formRef: RefObject<FormInstance>
}

interface RecordType {
  key: string;
  title: string;
  description?: string;
}

export const useAnomalyForm = ({ datasetOptions, activeTag, onSuccess, formRef }: UseAnomalyFormProps) => {
  const { t } = useTranslation();
  const [key] = activeTag;
  const {
    addAnomalyTrainTask,
    updateAnomalyTrainTask,
    addLogClusteringTrainTask,
    updateLogClusteringTrainTask,
    addTimeSeriesTrainTask,
    updateTimeSeriesTrainTask,
    addClassificationTrainTask,
    updateClassificationTrainTask
  } = useMlopsTaskApi();
  const { loadTrainOptions, getDatasetByTrainId } = useTrainDataLoader();
  const { hyperoptConversion, renderParams } = useParamsUtil();
  // const formRef = useRef<FormInstance>(null);
  const [modalState, setModalState] = useState<ModalState>({
    isOpen: false,
    type: 'add',
    title: 'addtask',
  });
  const [formData, setFormData] = useState<TrainJob | null>(null);
  const [loadingState, setLoadingState] = useState<{
    confirm: boolean,
    dataset: boolean,
    select: boolean,
    transfer: boolean
  }>({
    confirm: false,
    dataset: false,
    select: false,
    transfer: false
  });
  const [traindataOption, setTrainDataOption] = useState<{
    trainOption: Option[],
    valOption: Option[],
    testOption: Option[],
  }>({
    trainOption: [],
    valOption: [],
    testOption: []
  });
  const [isShow, setIsShow] = useState<boolean>(false);
  const [algorithmType, setAlgorithmsType] = useState<string>('');
  const [selectedColumns, setSelectedColumns] = useState<RecordType[]>([]);
  const [targetKeys, setTargetKeys] = useState<TransferProps['targetKeys']>([]);
  const [selectedKeys, setSelectedKeys] = useState<TransferProps['targetKeys']>([]);
  const addTrainTask: Record<string, any> = {
    'anomaly': addAnomalyTrainTask,
    'log_clustering': addLogClusteringTrainTask,
    'timeseries_predict': addTimeSeriesTrainTask,
    'classification': addClassificationTrainTask
  };
  const updateTrainTask: Record<string, any> = {
    'anomaly': updateAnomalyTrainTask,
    'log_clustering': updateLogClusteringTrainTask,
    'timeseries_predict': updateTimeSeriesTrainTask,
    'classification': updateClassificationTrainTask
  };
  const algorithmOptions: Record<string, Option[]> = {
    'anomaly': [
      { value: 'RandomForest', label: `RandomForest` },
    ],
    'log_clustering': [
      { value: 'KMeans', label: 'KMeans' },
      { value: 'DBSCAN', label: 'DBSCAN' },
      { value: 'AgglomerativeClustering', label: '层次聚类' },
      { value: 'Drain', label: 'Drain' },
      { value: 'LogCluster', label: 'LogCluster' },
    ],
    'timeseries_predict': [
      { value: 'Prophet', label: 'Prophet' }
    ],
    'classification': [
      { value: 'RandomForest', label: `RandomForest` },
    ]
  };

  // 当 formData 和 modalState.isOpen 改变时初始化表单
  useEffect(() => {
    if (formData && modalState.isOpen) {
      initializeForm(formData);
    }
  }, [modalState.isOpen, formData]);

  // 显示模态框
  const showModal = useCallback(({ type, title, form }: { type: string; title: string; form: any }) => {
    setLoadingState((prev) => ({ ...prev, select: false }));
    setFormData(form);
    setModalState({
      isOpen: true,
      type,
      title: title as string,
    });
  }, []);

  // 初始化表单
  const initializeForm = async (formData: TrainJob) => {
    if (key === 'rasa') return;
    // const defaultParams: Record<string, any> = {};
    // ALGORITHMS_PARAMS[algorithmType].forEach(item => {
    //   defaultParams[item.name] = item.default;
    // });
    if (!formRef.current) return;
    formRef.current.resetFields();

    if (modalState.type === 'add') {
      // formRef.current.setFieldsValue({
      //   hyperopt_config: defaultParams
      // });
    } else if (formData) {
      setAlgorithmsType(formData.algorithm);
      const immediateData = {
        name: formData.name,
        type: formData.type,
        max_evals: formData.max_evals,
        algorithm: formData.algorithm,
        hyperopt_config: hyperoptConversion(formData.hyperopt_config)
      };

      formRef.current.setFieldsValue(immediateData);
      setIsShow(true);
      handleAsyncDataLoading(formData.train_data_id as number, formData);
    }
  };

  const onTrainSelectChange = async (value: number) => {
    if (!value) return;
    try {
      if(key !== 'classification') return;
      setLoadingState(prev => ({...prev, transfer: true}));
      const { metadata } = await getDatasetByTrainId(value, key);
      if (key === 'classification' && metadata.headers) {
        const _headers = metadata.headers?.map((item: string, index: number) => ({
          key: index,
          title: item
        })).slice(0, metadata.headers?.length - 1);
        setSelectedColumns(_headers);
        setTargetKeys(_headers.map((item: any) => item.key));
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({...prev, transfer: false}));
    }
  };

  // 以训练文件ID获取数据ID
  const handleAsyncDataLoading = useCallback(async (trainDataId: number, formData: TrainJob) => {
    if (!trainDataId) return;
    setLoadingState((prev) => ({ ...prev, select: true }));
    try {
      const { dataset } = await getDatasetByTrainId(formData.train_data_id as number, key);
      if (dataset && formRef.current) {
        formRef.current.setFieldsValue({
          dataset_id: dataset
        });

        await renderOptions(dataset);
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [getDatasetByTrainId]);

  // 渲染文件选项
  const renderOptions = useCallback(async (dataset: number) => {
    setLoadingState(prev => ({ ...prev, select: true }));
    try {
      if (!formRef.current || !dataset) return;
      // 加载训练数据选项
      const trainOptions = await loadTrainOptions(dataset, key);
      onTrainSelectChange(formData?.train_data_id as number);
      setTrainDataOption(trainOptions);
      formRef.current.setFieldsValue({
        train_data_id: formData?.train_data_id,
        val_data_id: formData?.val_data_id,
        test_data_id: formData?.test_data_id,
      });
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [loadTrainOptions, formData]);

  // 穿梭框控制操作
  const onChange: TransferProps['onChange'] = (nextTargetKeys) => {
    setTargetKeys(nextTargetKeys);
  };

  const onSelectChange: TransferProps['onSelectChange'] = (sourceSelectedKeys, targetSelectedKeys) => {
    setSelectedKeys([...sourceSelectedKeys, ...targetSelectedKeys])
  };



  // 渲染超参数表单项
  const renderItem = useCallback((param: AlgorithmParam[]) => {
    if (!param) return [];
    return param.map((item) => (
      <Form.Item key={item.name} name={['hyperopt_config', item.name]} label={item.name} rules={[{ required: true, message: t('common.inputMsg') }]}>
        {item.type === 'randint' ?
          <RangeInput className='ml-2' value={item.default as [number, number]} /> :
          <Select className='ml-2' mode="multiple" options={item.options} />
        }
      </Form.Item>
    ));
  }, [t]);

  // 算法变化
  const onTypeChange = useCallback((value: string) => {
    if (!formRef.current) return;
    const defaultParams: Record<string, any> = {};
    ALGORITHMS_PARAMS[value].forEach(item => {
      defaultParams[item.name] = item.default;
    });
    formRef.current.setFieldsValue({
      hyperopt_config: defaultParams
    });
    setAlgorithmsType(value);
    setIsShow(true);
  }, []);

  // 提交处理
  const handleSubmit = useCallback(async () => {
    if (loadingState.confirm) return;
    setLoadingState((prev) => ({ ...prev, confirm: true }));

    try {
      const value = await formRef.current?.validateFields();
      const hyperopt_config = renderParams(value?.hyperopt_config, algorithmType);
      const params = {
        ...value,
        status: 'pending',
        hyperopt_config,
        description: value.name || ''
      };
      if(key === 'classification') {
        params['selected_columns'] = selectedColumns.filter(item => targetKeys?.includes(item.key)).map(item => item.title);
      }
      console.log(params);

      if (modalState.type === 'add') {
        await addTrainTask[key](params);

      } else {
        await updateTrainTask[key](formData?.id as string, params);
      }

      setModalState((prev) => ({ ...prev, isOpen: false }));
      message.success(t(`common.${modalState.type}Success`));
      setIsShow(false);
      onSuccess();
    } catch (e) {
      console.log(e);
      message.error(t(`common.error`));
    } finally {
      setLoadingState((prev) => ({ ...prev, confirm: false }));
    }
  }, [modalState.type, formData, onSuccess, addAnomalyTrainTask, updateAnomalyTrainTask, renderParams, t]);

  const transferVaildate = useCallback(() => {
    if(targetKeys?.length === 0) {
      return Promise.reject(new Error(`请至少选择一个列用于训练`))
    }
    return Promise.resolve();
  }, [t])

  // 取消处理
  const handleCancel = useCallback(() => {
    setModalState({
      isOpen: false,
      type: 'add',
      title: 'addtask',
    });
    formRef.current?.resetFields();
    setTrainDataOption({
      trainOption: [],
      valOption: [],
      testOption: []
    });
    setSelectedColumns([]);
    setIsShow(false);
  }, []);

  // 渲染表单内容
  const renderFormContent = useCallback(() => {
    // if (key !== 'anomaly') return;
    return (
      <>
        <Form.Item
          name='name'
          label={t('common.name')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name='algorithm'
          label={t('traintask.algorithms')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Select placeholder={t('traintask.selectAlgorithmsMsg')} onChange={onTypeChange} options={algorithmOptions[key]} />
        </Form.Item>
        <Form.Item
          name='max_evals'
          label={t('traintask.maxEvals')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <InputNumber style={{ width: '100%' }} placeholder={t('traintask.maxEvalsMsg')} />
        </Form.Item>
        <Form.Item
          name='dataset_id'
          label={t('traintask.datasets')}
          rules={[{ required: true, message: t('traintask.selectDatasets') }]}
        >
          <Select placeholder={t('traintask.selectDatasets')} loading={loadingState.select} options={datasetOptions} onChange={renderOptions} />
        </Form.Item>
        {isShow && (
          <>
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              {t(`traintask.trainfile`)}
            </Divider>
            <Form.Item
              name='train_data_id'
              className='ml-2'
              label={t('datasets.train')}
              rules={[{ required: true, message: t('common.selectMsg') }]}
            >
              <Select placeholder={t('common.selectMsg')} loading={loadingState.select} options={traindataOption.trainOption} onChange={(value) => onTrainSelectChange(value)} />
            </Form.Item>
            <Form.Item
              name='val_data_id'
              className='ml-2'
              label={t('datasets.validate')}
              rules={[{ required: true, message: t('common.selectMsg') }]}
            >
              <Select placeholder={t('common.selectMsg')} loading={loadingState.select} options={traindataOption.valOption} />
            </Form.Item>
            <Form.Item
              name='test_data_id'
              className='ml-2'
              label={t('datasets.test')}
              rules={[{ required: true, message: t('common.selectMsg') }]}
            >
              <Select placeholder={t('common.selectMsg')} loading={loadingState.select} options={traindataOption.testOption} />
            </Form.Item>
            {key === 'classification' &&
              <Form.Item
                name='selected_columns'
                className='ml-2'
                label={t(`traintask.selectedColumns`)}
                rules={[{ required: true, validator: transferVaildate }]}
              >
                <Spin spinning={loadingState.transfer}>
                  <Transfer
                    rootClassName='justify-center'
                    dataSource={selectedColumns}
                    titles={['未使用', '已使用']}
                    targetKeys={targetKeys}
                    selectedKeys={selectedKeys}
                    onChange={onChange}
                    onSelectChange={onSelectChange}
                    render={(item) => item.title}
                  />
                </Spin>
              </Form.Item>
            }
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              {t(`traintask.hyperopt`)}
            </Divider>
            {renderItem(ALGORITHMS_PARAMS[algorithmType])}
          </>
        )}
      </>
    );
  }, [t, onTypeChange, loadingState.select, datasetOptions, renderOptions, isShow, traindataOption, renderItem]);

  return {
    modalState,
    formRef,
    loadingState,
    showModal,
    handleSubmit,
    handleCancel,
    renderFormContent,
  };
};
